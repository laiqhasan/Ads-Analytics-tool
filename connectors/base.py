from datetime import date
from typing import Protocol, List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AccountDto(BaseModel):
    account_id: str
    provider: str
    client_name: str
    currency: str
    timezone: str

class EntityDto(BaseModel):
    provider: str
    account_id: str
    level: str  # 'campaign' | 'adgroup' | 'ad' | 'keyword' | 'search_term'
    native_id: str
    parent_key: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None  # 'active' | 'paused' | 'removed'
    raw: Optional[Dict[str, Any]] = None

    @property
    def entity_key(self) -> str:
        return f"{self.provider}:{self.account_id}:{self.level}:{self.native_id}"

class MetricRowDto(BaseModel):
    entity_key: str
    provider: str
    account_id: str
    level: str
    date: date
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0  # Normalized (e.g. converted from micros to actual currency)
    conversions: float = 0.0
    conv_value: float = 0.0
    raw: Optional[Dict[str, Any]] = None

class AdsConnector(Protocol):
    @property
    def provider(self) -> str:
        """Return the provider name (e.g., 'google', 'meta')"""
        ...

    def list_accounts(self) -> List[AccountDto]:
        """Fetch all connected ad accounts for this provider"""
        ...

    def fetch_entities(self, account_id: str, level: str) -> List[EntityDto]:
        """Fetch all entities (campaigns, adgroups, ads, etc.) for a specific account and level"""
        ...

    def fetch_metrics(self, account_id: str, level: str, start: date, end: date) -> List[MetricRowDto]:
        """Fetch metrics (impressions, clicks, cost, conversions) for a specific account, level, and date range"""
        ...

    def add_negative_keyword(self, account_id: str, campaign_id: str, keyword: str) -> bool:
        """Add a negative keyword to a campaign"""
        ...

    def pause_entity(self, account_id: str, level: str, native_id: str) -> bool:
        """Pause a campaign, ad group (adset), or ad"""
        ...

    def update_budget(self, account_id: str, campaign_id: str, new_budget: float) -> bool:
        """Update a campaign's daily budget"""
        ...

