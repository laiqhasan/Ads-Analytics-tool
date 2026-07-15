import hashlib
import logging
from datetime import date, timedelta
from typing import List, Optional
from connectors.base import AdsConnector, AccountDto, EntityDto, MetricRowDto

logger = logging.getLogger(__name__)

class MockConnector(AdsConnector):
    def __init__(self, provider_name: str = "google"):
        self._provider = provider_name

    @property
    def provider(self) -> str:
        return self._provider

    def list_accounts(self) -> List[AccountDto]:
        if self.provider == "google":
            return [
                AccountDto(
                    account_id="123-456-7890",
                    provider=self.provider,
                    client_name="Acme Corp (US)",
                    currency="USD",
                    timezone="America/New_York"
                ),
                AccountDto(
                    account_id="987-654-3210",
                    provider=self.provider,
                    client_name="Beta Corp (EU)",
                    currency="EUR",
                    timezone="Europe/Paris"
                )
            ]
        else:  # meta
            return [
                AccountDto(
                    account_id="act_101202303404505",
                    provider=self.provider,
                    client_name="Acme Corp Meta (US)",
                    currency="USD",
                    timezone="America/New_York"
                ),
                AccountDto(
                    account_id="act_909808707605504",
                    provider=self.provider,
                    client_name="Beta Corp Meta (EU)",
                    currency="EUR",
                    timezone="Europe/Paris"
                )
            ]

    def _get_mock_entities(self, account_id: str, level: str) -> List[EntityDto]:
        entities = []
        if level == "campaign":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="campaign",
                    native_id="camp-101",
                    name="US - Prospecting - Broad Match",
                    status="active",
                    raw={"bid_strategy": "Maximize Conversions"}
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="campaign",
                    native_id="camp-102",
                    name="US - Brand - Exact",
                    status="active",
                    raw={"bid_strategy": "Target CPA"}
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="campaign",
                    native_id="camp-103",
                    name="US - Remarketing - Display",
                    status="paused",
                    raw={"bid_strategy": "Manual CPC"}
                )
            ]
        elif level == "adgroup":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="adgroup",
                    native_id="adg-201",
                    parent_key=f"{self.provider}:{account_id}:campaign:camp-101",
                    name="Widgets Search",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="adgroup",
                    native_id="adg-202",
                    parent_key=f"{self.provider}:{account_id}:campaign:camp-101",
                    name="Gizmos Search",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="adgroup",
                    native_id="adg-203",
                    parent_key=f"{self.provider}:{account_id}:campaign:camp-102",
                    name="Brand Keywords",
                    status="active"
                )
            ]
        elif level == "ad":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="ad",
                    native_id="ad-301",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-201",
                    name="Widgets Search Responsive Ad 1",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="ad",
                    native_id="ad-302",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-203",
                    name="Brand Keyword Responsive Ad 1",
                    status="active"
                )
            ]
        elif level == "keyword":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="keyword",
                    native_id="kw-401",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-201",
                    name="buy widgets online",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="keyword",
                    native_id="kw-402",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-203",
                    name="acme widgets coupon",
                    status="active"
                )
            ]
        elif level == "search_term":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="search_term",
                    native_id="st-501",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-201",
                    name="cheap widgets for sale",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="search_term",
                    native_id="st-502",
                    parent_key=f"{self.provider}:{account_id}:adgroup:adg-201",
                    name="free widgets",
                    status="active"
                )
            ]
        return entities

    def fetch_entities(self, account_id: str, level: str) -> List[EntityDto]:
        return self._get_mock_entities(account_id, level)

    def fetch_metrics(self, account_id: str, level: str, start: date, end: date) -> List[MetricRowDto]:
        metrics = []
        entities = self._get_mock_entities(account_id, level)
        
        current_date = start
        while current_date <= end:
            for entity in entities:
                # Generate deterministic values based on date and entity
                seed_str = f"{entity.entity_key}:{current_date.isoformat()}"
                seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
                
                # Base performance by level and status
                if entity.status == "paused":
                    impressions = 0
                    clicks = 0
                    cost = 0.0
                    conversions = 0.0
                    conv_value = 0.0
                else:
                    # Deterministic but pseudo-random ranges
                    impressions = 100 + (seed_hash % 900)
                    # Clicks depend on CTR (say 2% to 15%)
                    ctr = 0.02 + ((seed_hash % 13) / 100.0)
                    clicks = int(impressions * ctr)
                    # Cost is average CPC of $0.50 to $4.00
                    cpc = 0.50 + ((seed_hash % 350) / 100.0)
                    cost = round(clicks * cpc, 4)
                    
                    # Conversions depend on conversion rate (say 0% to 10%)
                    conv_rate = 0.0 + ((seed_hash % 11) / 100.0)
                    conversions = round(clicks * conv_rate, 2)
                    # Conv value is conversions * average value of $20 to $100
                    avg_value = 20.0 + (seed_hash % 80)
                    conv_value = round(conversions * avg_value, 4)
                
                metrics.append(
                    MetricRowDto(
                        entity_key=entity.entity_key,
                        provider=self.provider,
                        account_id=account_id,
                        level=level,
                        date=current_date,
                        impressions=impressions,
                        clicks=clicks,
                        cost=cost,
                        conversions=conversions,
                        conv_value=conv_value,
                        raw={"source": "mock_generator", "ctr": ctr if 'ctr' in locals() else 0.0}
                    )
                )
            current_date += timedelta(days=1)
            
        return metrics

    def add_negative_keyword(self, account_id: str, campaign_id: str, keyword: str) -> bool:
        logger.info(f"[MOCK WRITE] Added negative keyword '{keyword}' to campaign '{campaign_id}' in account '{account_id}'")
        return True

    def pause_entity(self, account_id: str, level: str, native_id: str) -> bool:
        logger.info(f"[MOCK WRITE] Paused entity '{native_id}' of level '{level}' in account '{account_id}'")
        return True

    def update_budget(self, account_id: str, campaign_id: str, new_budget: float) -> bool:
        logger.info(f"[MOCK WRITE] Updated campaign '{campaign_id}' budget to ${new_budget} in account '{account_id}'")
        return True

