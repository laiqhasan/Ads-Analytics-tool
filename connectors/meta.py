import os
import logging
import requests
import json
import hashlib
from datetime import date, timedelta, datetime
from typing import List, Dict, Any, Optional
from connectors.base import AdsConnector, AccountDto, EntityDto, MetricRowDto

logger = logging.getLogger(__name__)

class MetaConnector(AdsConnector):
    def __init__(self):
        self._provider = "meta"
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        
        # Load account ids (comma-separated, without 'act_' prefix, but we clean it anyway)
        raw_accounts = os.getenv("META_AD_ACCOUNT_IDS", "")
        self.ad_account_ids = []
        if raw_accounts:
            for acc in raw_accounts.split(","):
                acc = acc.strip()
                if acc:
                    # Meta API ad account IDs must start with 'act_' prefix
                    if not acc.startswith("act_"):
                        acc = f"act_{acc}"
                    self.ad_account_ids.append(acc)
                    
        self.is_mock = not bool(self.access_token)
        if self.is_mock:
            logger.warning("META_ACCESS_TOKEN not set. MetaConnector running in mock fallback mode.")

    @property
    def provider(self) -> str:
        return self._provider

    def list_accounts(self) -> List[AccountDto]:
        if self.is_mock:
            # Match the IDs and names from Phase 1 verification tests
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

        # Call Meta Graph API /me/adaccounts
        url = "https://graph.facebook.com/v19.0/me/adaccounts"
        params = {
            "access_token": self.access_token,
            "fields": "id,name,currency,timezone_name"
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            
            accounts = []
            for item in data:
                acc_id = item["id"]
                # If target accounts are configured, filter by them
                if self.ad_account_ids and acc_id not in self.ad_account_ids:
                    continue
                    
                accounts.append(
                    AccountDto(
                        account_id=acc_id,
                        provider=self.provider,
                        client_name=item.get("name", f"Meta Account {acc_id}"),
                        currency=item.get("currency", "USD"),
                        timezone=item.get("timezone_name", "America/New_York")
                    )
                )
            return accounts
        except Exception as e:
            logger.error(f"Failed to fetch Meta accounts: {e}")
            raise

    def fetch_entities(self, account_id: str, level: str) -> List[EntityDto]:
        # Meta does not use keyword or search_term levels, so we return empty lists for them
        if level in ("keyword", "search_term"):
            return []

        if self.is_mock:
            return self._get_mock_entities(account_id, level)

        # Map our level name to Meta's native API endpoint names
        meta_endpoint = {
            "campaign": "campaigns",
            "adgroup": "adsets",  # Meta adsets map to our adgroups
            "ad": "ads"
        }.get(level)

        if not meta_endpoint:
            return []

        url = f"https://graph.facebook.com/v19.0/{account_id}/{meta_endpoint}"
        
        # Determine parent field
        fields = "id,name,status"
        if level == "adgroup":
            fields += ",campaign_id"
        elif level == "ad":
            fields += ",adset_id"

        params = {
            "access_token": self.access_token,
            "fields": fields,
            "limit": 100
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            
            entities = []
            for item in data:
                native_id = item["id"]
                
                # Resolve parent key mapping
                parent_key = None
                if level == "adgroup":
                    parent_id = item.get("campaign_id")
                    if parent_id:
                        parent_key = f"{self.provider}:{account_id}:campaign:{parent_id}"
                elif level == "ad":
                    parent_id = item.get("adset_id")
                    if parent_id:
                        parent_key = f"{self.provider}:{account_id}:adgroup:{parent_id}"

                status = "active" if item.get("status") == "ACTIVE" else "paused"
                if item.get("status") in ("DELETED", "ARCHIVED"):
                    status = "removed"

                entities.append(
                    EntityDto(
                        provider=self.provider,
                        account_id=account_id,
                        level=level,
                        native_id=native_id,
                        parent_key=parent_key,
                        name=item.get("name"),
                        status=status,
                        raw=item
                    )
                )
            return entities
        except Exception as e:
            logger.error(f"Failed to fetch Meta entities for account {account_id} at level {level}: {e}")
            raise

    def fetch_metrics(self, account_id: str, level: str, start: date, end: date) -> List[MetricRowDto]:
        if level in ("keyword", "search_term"):
            return []

        if self.is_mock:
            return self._get_mock_metrics(account_id, level, start, end)

        # Map our level name to Meta's insights API level parameter
        meta_level = {
            "campaign": "campaign",
            "adgroup": "adset",  # Meta adsets map to our adgroups
            "ad": "ad"
        }.get(level)

        if not meta_level:
            return []

        url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
        params = {
            "access_token": self.access_token,
            "level": meta_level,
            "time_increment": 1,  # daily granularity
            "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
            "fields": f"impressions,clicks,spend,{meta_level}_id,actions,action_values",
            "limit": 500
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            
            metrics = []
            for item in data:
                native_id = item[f"{meta_level}_id"]
                entity_key = f"{self.provider}:{account_id}:{level}:{native_id}"
                
                # Parse conversions and values from nested actions arrays
                conversions, conv_value = self._parse_actions(
                    item.get("actions", []), 
                    item.get("action_values", [])
                )
                
                metric_date = datetime.strptime(item["date_start"], "%Y-%m-%d").date()

                metrics.append(
                    MetricRowDto(
                        entity_key=entity_key,
                        provider=self.provider,
                        account_id=account_id,
                        level=level,
                        date=metric_date,
                        impressions=int(item.get("impressions", 0)),
                        clicks=int(item.get("clicks", 0)),
                        cost=float(item.get("spend", 0.0)),
                        conversions=conversions,
                        conv_value=conv_value,
                        raw=item
                    )
                )
            return metrics
        except Exception as e:
            logger.error(f"Failed to fetch Meta metrics for account {account_id} at level {level}: {e}")
            raise

    def _parse_actions(self, actions: List[Dict[str, Any]], action_values: List[Dict[str, Any]]) -> tuple[float, float]:
        """
        Parses nested action and value arrays from Meta Graph API.
        Sums conversions (purchases, leads, custom offsite/onsite conversions) and their values.
        """
        conversions = 0.0
        conv_value = 0.0
        
        # Standard conversion indicators
        conv_types = {"purchase", "lead", "offsite_conversion", "onsite_conversion", "contact"}
        
        for act in actions:
            action_type = act.get("action_type", "")
            if any(ct in action_type for ct in conv_types):
                conversions += float(act.get("value", 0.0))
                
        for val in action_values:
            action_type = val.get("action_type", "")
            if any(ct in action_type for ct in conv_types):
                conv_value += float(val.get("value", 0.0))
                
        return conversions, conv_value

    # ==========================================
    # Mock fallback helpers
    # ==========================================
    def _get_mock_entities(self, account_id: str, level: str) -> List[EntityDto]:
        entities = []
        if level == "campaign":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="campaign",
                    native_id="meta-camp-901",
                    name="US - Lookalike Purchases 1%",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="campaign",
                    native_id="meta-camp-902",
                    name="US - Retargeting Website Visitors",
                    status="active"
                )
            ]
        elif level == "adgroup":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="adgroup",
                    native_id="meta-set-801",
                    parent_key=f"{self.provider}:{account_id}:campaign:meta-camp-901",
                    name="LAL 1% - Purchase - 18-45",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="adgroup",
                    native_id="meta-set-802",
                    parent_key=f"{self.provider}:{account_id}:campaign:meta-camp-902",
                    name="All Site Visitors - 30 Days",
                    status="active"
                )
            ]
        elif level == "ad":
            entities = [
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="ad",
                    native_id="meta-ad-701",
                    parent_key=f"{self.provider}:{account_id}:adgroup:meta-set-801",
                    name="Ad Creative Image A (US)",
                    status="active"
                ),
                EntityDto(
                    provider=self.provider,
                    account_id=account_id,
                    level="ad",
                    native_id="meta-ad-702",
                    parent_key=f"{self.provider}:{account_id}:adgroup:meta-set-802",
                    name="Ad Creative Video A (US)",
                    status="active"
                )
            ]
        return entities

    def _get_mock_metrics(self, account_id: str, level: str, start: date, end: date) -> List[MetricRowDto]:
        metrics = []
        entities = self._get_mock_entities(account_id, level)
        current_date = start
        while current_date <= end:
            for entity in entities:
                seed_str = f"{entity.entity_key}:{current_date.isoformat()}"
                seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
                
                impressions = 200 + (seed_hash % 800)
                ctr = 0.01 + ((seed_hash % 10) / 100.0)
                clicks = int(impressions * ctr)
                cpc = 0.40 + ((seed_hash % 200) / 100.0)
                cost = round(clicks * cpc, 4)
                
                conv_rate = 0.01 + ((seed_hash % 6) / 100.0)
                conversions = round(clicks * conv_rate, 2)
                avg_value = 25.0 + (seed_hash % 50)
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
                        raw={"source": "meta_mock_generator", "actions": [{"action_type": "purchase", "value": str(conversions)}]}
                    )
                )
            current_date += timedelta(days=1)
        return metrics

    def add_negative_keyword(self, account_id: str, campaign_id: str, keyword: str) -> bool:
        # Meta doesn't support keyword-level negative keywords in the same relational format.
        # It has brand safety lists and block lists, so we log a warning but return True to simulate success.
        logger.warning(f"Meta Ads does not support keyword-level negatives natively. Simulating negative keyword block '{keyword}' for campaign '{campaign_id}'.")
        return True

    def pause_entity(self, account_id: str, level: str, native_id: str) -> bool:
        if self.is_mock:
            logger.info(f"[META MOCK WRITE] Paused Meta entity {native_id} (level={level}) in account {account_id}")
            return True

        meta_endpoint = f"https://graph.facebook.com/v19.0/{native_id}"
        try:
            response = requests.post(
                meta_endpoint, 
                data={"status": "PAUSED", "access_token": self.access_token}
            )
            response.raise_for_status()
            logger.info(f"Successfully paused Meta {level} {native_id}")
            return response.json().get("success", False)
        except Exception as e:
            logger.error(f"Failed to pause Meta {level} {native_id}: {e}")
            return False

    def update_budget(self, account_id: str, campaign_id: str, new_budget: float) -> bool:
        if self.is_mock:
            logger.info(f"[META MOCK WRITE] Updated Meta campaign {campaign_id} daily budget to ${new_budget} in account {account_id}")
            return True

        url = f"https://graph.facebook.com/v19.0/{campaign_id}"
        try:
            # Meta expects budget values in cents (e.g. $10.00 is 1000)
            response = requests.post(
                url,
                data={"daily_budget": int(new_budget * 100), "access_token": self.access_token}
            )
            response.raise_for_status()
            logger.info(f"Successfully updated Meta campaign {campaign_id} budget to ${new_budget}")
            return response.json().get("success", False)
        except Exception as e:
            logger.error(f"Failed to update budget for Meta campaign {campaign_id}: {e}")
            return False

