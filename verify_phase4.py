import sys
from sqlalchemy import text
from db.session import SessionLocal
from db.models import Account, Entity, MetricDaily
from connectors.meta import MetaConnector
from sync.orchestrator import SyncOrchestrator

def run_verification():
    print("=== STARTING PHASE 4 META ADS VERIFICATION ===")
    
    # 1. Sync Meta data using MetaConnector (falls back to mock mode if credentials aren't set)
    print("\n[1] Running Sync Orchestrator with MetaConnector...")
    connector = MetaConnector()
    orchestrator = SyncOrchestrator(SessionLocal, [connector])
    # Sync a 7-day lookback window
    orchestrator.sync(lookback_days=7)
    
    session = SessionLocal()
    try:
        # 2. Verify Accounts
        print("\n[2] Verifying Meta accounts in database...")
        meta_accounts = session.query(Account).filter_by(provider="meta").all()
        print(f"   -> Meta accounts count: {len(meta_accounts)}")
        for acc in meta_accounts:
            print(f"      * Account: ID={acc.account_id} | Name='{acc.client_name}' | Currency={acc.currency}")
        assert len(meta_accounts) == 2, "Expected 2 Meta mock accounts to be imported"
        
        # 3. Verify Entities Mapping (Meta campaigns, adsets -> adgroups, ads)
        print("\n[3] Verifying Meta level and hierarchy mapping...")
        meta_entities = session.query(Entity).filter_by(provider="meta").all()
        print(f"   -> Mapped Meta entities count: {len(meta_entities)}")
        
        campaigns = [e for e in meta_entities if e.level == "campaign"]
        adgroups = [e for e in meta_entities if e.level == "adgroup"]
        ads = [e for e in meta_entities if e.level == "ad"]
        keywords = [e for e in meta_entities if e.level == "keyword"]
        
        print(f"      * Campaigns (level='campaign'): {len(campaigns)}")
        print(f"      * Ad Sets (mapped to level='adgroup'): {len(adgroups)}")
        print(f"      * Ads (level='ad'): {len(ads)}")
        print(f"      * Keywords (level='keyword'): {len(keywords)}")
        
        assert len(campaigns) > 0, "Expected at least 1 Meta campaign"
        assert len(adgroups) > 0, "Expected Meta adsets to be mapped as adgroups"
        assert len(ads) > 0, "Expected at least 1 Meta ad"
        assert len(keywords) == 0, "Expected 0 Meta keywords (not supported in Meta)"
        
        # Verify Parent/Child hierarchy mapping
        # Ad parent_key should point to Ad Set (adgroup), Ad Set parent_key should point to Campaign
        test_ad = ads[0]
        print(f"      * Checking ad hierarchy: Ad '{test_ad.name}' parent key is '{test_ad.parent_key}'")
        assert test_ad.parent_key is not None, "Expected parent key relation for ad"
        assert ":adgroup:" in test_ad.parent_key, f"Expected parent key to point to an adgroup, got '{test_ad.parent_key}'"
        
        test_adgroup = adgroups[0]
        print(f"      * Checking ad group hierarchy: AdGroup '{test_adgroup.name}' parent key is '{test_adgroup.parent_key}'")
        assert test_adgroup.parent_key is not None, "Expected parent key relation for adgroup"
        assert ":campaign:" in test_adgroup.parent_key, f"Expected parent key to point to a campaign, got '{test_adgroup.parent_key}'"
        
        # 4. Verify Metrics parsing (Nested actions -> conversions/conv_value)
        print("\n[4] Verifying daily metrics parsing from Meta actions array...")
        meta_metrics = session.query(MetricDaily).filter_by(provider="meta").all()
        print(f"   -> Mapped daily metrics rows count: {len(meta_metrics)}")
        assert len(meta_metrics) > 0, "Expected daily metric rows to be synced"
        
        # Show a sample
        sample = meta_metrics[0]
        print(f"      * Metric Sample: Date={sample.date} | Cost=${sample.cost:.2f} | Conversions={sample.conversions} | Value=${sample.conv_value:.2f}")
        assert sample.conversions > 0, "Expected conversions to be parsed and mapped"
        assert sample.conv_value > 0.0, "Expected conversion value to be parsed and mapped"
        
        print("\n=== PHASE 4 META ADS VERIFICATION SUCCESSFUL ===")
    except Exception as e:
        print(f"\n!!! PHASE 4 META ADS VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    run_verification()
