import logging
from datetime import date, timedelta
from typing import List, Callable
from sqlalchemy.orm import Session
from db.models import Account, Entity, MetricDaily
from connectors.base import AdsConnector, AccountDto, EntityDto, MetricRowDto

logger = logging.getLogger(__name__)

class SyncOrchestrator:
    def __init__(self, session_factory: Callable[[], Session], connectors: List[AdsConnector]):
        """
        Initialize the orchestrator.
        
        :param session_factory: A callable that returns a SQLAlchemy Session instance.
        :param connectors: List of connectors implementing the AdsConnector Protocol.
        """
        self.session_factory = session_factory
        self.connectors = connectors

    def sync(self, lookback_days: int = 30):
        """
        Execute the daily sync process.
        Iterates through all connectors, pulls metadata and metrics, and upserts them.
        
        :param lookback_days: Number of days to re-pull for late-attributed conversions.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)
        logger.info(f"Starting sync job: lookback of {lookback_days} days (from {start_date} to {end_date})")

        for connector in self.connectors:
            logger.info(f"Syncing provider: {connector.provider}")
            try:
                accounts = connector.list_accounts()
            except Exception as e:
                logger.error(f"Error listing accounts for provider {connector.provider}: {e}", exc_info=True)
                continue

            for account_dto in accounts:
                logger.info(f"Starting sync for account: {account_dto.account_id} ({account_dto.client_name})")
                session = self.session_factory()
                try:
                    # 1. Upsert Account
                    self._upsert_account(session, account_dto)
                    session.flush()  # Flush so foreign key constraints on entities will succeed

                    levels = ["campaign", "adgroup", "ad", "keyword", "search_term"]

                    # 2. Sync Entities (metadata) for all levels
                    for level in levels:
                        logger.info(f"Syncing entities at level '{level}' for account {account_dto.account_id}")
                        entities = connector.fetch_entities(account_dto.account_id, level)
                        self._upsert_entities(session, entities)
                        session.flush()

                    # 3. Sync Metrics for all levels for the lookback window
                    for level in levels:
                        logger.info(f"Syncing metrics at level '{level}' for account {account_dto.account_id} ({start_date} to {end_date})")
                        metrics = connector.fetch_metrics(account_dto.account_id, level, start_date, end_date)
                        self._upsert_metrics(session, metrics)
                        session.flush()

                    session.commit()
                    logger.info(f"Completed sync for account: {account_dto.account_id}")
                except Exception as e:
                    session.rollback()
                    logger.error(f"Transaction rolled back. Failed to sync account {account_dto.account_id}: {e}", exc_info=True)
                finally:
                    session.close()

    def _upsert_account(self, session: Session, dto: AccountDto):
        """Upsert an account record."""
        acc = session.query(Account).filter_by(account_id=dto.account_id).first()
        if acc:
            acc.provider = dto.provider
            acc.client_name = dto.client_name
            acc.currency = dto.currency
            acc.timezone = dto.timezone
        else:
            acc = Account(
                account_id=dto.account_id,
                provider=dto.provider,
                client_name=dto.client_name,
                currency=dto.currency,
                timezone=dto.timezone
            )
            session.add(acc)

    def _upsert_entities(self, session: Session, dtos: List[EntityDto]):
        """Batch upsert entities, minimizing DB hits by loading existing ones first."""
        if not dtos:
            return

        entity_keys = [dto.entity_key for dto in dtos]
        existing = {
            e.entity_key: e
            for e in session.query(Entity).filter(Entity.entity_key.in_(entity_keys)).all()
        }

        for dto in dtos:
            key = dto.entity_key
            if key in existing:
                ent = existing[key]
                ent.name = dto.name
                ent.status = dto.status
                ent.parent_key = dto.parent_key
                ent.raw = dto.raw
            else:
                ent = Entity(
                    entity_key=key,
                    provider=dto.provider,
                    account_id=dto.account_id,
                    level=dto.level,
                    native_id=dto.native_id,
                    parent_key=dto.parent_key,
                    name=dto.name,
                    status=dto.status,
                    raw=dto.raw
                )
                session.add(ent)

    def _upsert_metrics(self, session: Session, dtos: List[MetricRowDto]):
        """Batch upsert daily metrics. Leverages date-key mappings to handle composite primary keys."""
        if not dtos:
            return

        entity_keys = list(set(dto.entity_key for dto in dtos))
        existing_list = session.query(MetricDaily).filter(MetricDaily.entity_key.in_(entity_keys)).all()
        existing = {(m.entity_key, m.date): m for m in existing_list}

        for dto in dtos:
            key = (dto.entity_key, dto.date)
            if key in existing:
                met = existing[key]
                met.impressions = dto.impressions
                met.clicks = dto.clicks
                met.cost = dto.cost
                met.conversions = dto.conversions
                met.conv_value = dto.conv_value
                met.raw = dto.raw
            else:
                met = MetricDaily(
                    entity_key=dto.entity_key,
                    provider=dto.provider,
                    account_id=dto.account_id,
                    level=dto.level,
                    date=dto.date,
                    impressions=dto.impressions,
                    clicks=dto.clicks,
                    cost=dto.cost,
                    conversions=dto.conversions,
                    conv_value=dto.conv_value,
                    raw=dto.raw
                )
                session.add(met)
