from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, Numeric, Date, Index, JSON, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db.session import Base

class Account(Base):
    __tablename__ = "accounts"

    account_id = Column(String, primary_key=True)  # Provider's native account ID
    provider = Column(String, nullable=False)       # 'google' | 'meta'
    client_name = Column(String, nullable=False)    # Agency's label
    currency = Column(String, nullable=False)
    timezone = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entities = relationship("Entity", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account(account_id={self.account_id}, provider={self.provider}, client_name={self.client_name})>"


class Entity(Base):
    __tablename__ = "entities"

    entity_key = Column(String, primary_key=True)   # f"{provider}:{account_id}:{level}:{native_id}"
    provider = Column(String, nullable=False)
    account_id = Column(String, ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False)
    level = Column(String, nullable=False)          # 'campaign' | 'adgroup' | 'ad' | 'keyword' | 'search_term'
    native_id = Column(String, nullable=False)
    parent_key = Column(String, nullable=True)      # Link to parent entity (e.g. adgroup -> campaign)
    name = Column(String, nullable=True)
    status = Column(String, nullable=True)          # 'active' | 'paused' | 'removed'
    raw = Column(JSON, nullable=True)              # Provider-specific extras

    account = relationship("Account", back_populates="entities")
    metrics = relationship("MetricDaily", back_populates="entity")

    def __repr__(self) -> str:
        return f"<Entity(entity_key={self.entity_key}, level={self.level}, name={self.name})>"


class MetricDaily(Base):
    __tablename__ = "metrics_daily"

    entity_key = Column(String, ForeignKey("entities.entity_key", ondelete="CASCADE"), primary_key=True)
    provider = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    level = Column(String, nullable=False)
    date = Column(Date, primary_key=True)

    impressions = Column(BigInteger, default=0)
    clicks = Column(BigInteger, default=0)
    cost = Column(Numeric(14, 4), default=0.0)
    conversions = Column(Numeric(14, 4), default=0.0)
    conv_value = Column(Numeric(14, 4), default=0.0)
    raw = Column(JSON, nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    entity = relationship("Entity", back_populates="metrics")

    __table_args__ = (
        Index("idx_metrics_daily_account_level_date", "account_id", "level", "date"),
        Index("idx_metrics_daily_provider_date", "provider", "date"),
    )

    def __repr__(self) -> str:
        return f"<MetricDaily(entity_key={self.entity_key}, date={self.date}, cost={self.cost})>"


class AutomationProposal(Base):
    __tablename__ = "automation_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)  # 'add_negative_keyword' | 'pause_entity' | 'adjust_budget'
    target_entity_key = Column(String, ForeignKey("entities.entity_key", ondelete="CASCADE"), nullable=False)
    details = Column(JSON, nullable=True)         # holds params like {"keyword": "free widgets"}
    status = Column(String, nullable=False, default="pending")  # 'pending' | 'approved' | 'rejected' | 'executed'
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    entity = relationship("Entity")

    def __repr__(self) -> str:
        return f"<AutomationProposal(id={self.id}, action_type={self.action_type}, status={self.status})>"

