import sys
from sqlalchemy import func
from db.session import SessionLocal
from db.models import Account, Entity, MetricDaily
from connectors.mock import MockConnector
from sync.orchestrator import SyncOrchestrator

def verify():
    print("=== STARTING VERIFICATION ===")
    
    # 1. Run the sync orchestrator for both google and meta platforms
    print("\n[1] Running Sync Orchestrator for 'google' and 'meta' mock providers...")
    connectors = [
        MockConnector(provider_name="google"),
        MockConnector(provider_name="meta")
    ]
    orchestrator = SyncOrchestrator(SessionLocal, connectors)
    
    # Run sync for a 7-day lookback window to make validation fast
    orchestrator.sync(lookback_days=7)
    
    # 2. Inspect Database records
    print("\n[2] Verifying records in database...")
    session = SessionLocal()
    try:
        # Accounts verification
        accounts = session.query(Account).all()
        print(f"-> Total accounts: {len(accounts)}")
        for acc in accounts:
            print(f"   - {acc.provider.upper()} Account: ID={acc.account_id}, Name='{acc.client_name}', Currency={acc.currency}")
            
        assert len(accounts) == 4, f"Expected 4 mock accounts (2 Google + 2 Meta), found {len(accounts)}"
        
        # Entities verification
        entities = session.query(Entity).all()
        print(f"-> Total entities: {len(entities)}")
        levels = ["campaign", "adgroup", "ad", "keyword", "search_term"]
        for level in levels:
            lvl_count = session.query(Entity).filter_by(level=level).count()
            print(f"   - Level '{level}': {lvl_count} entities")
            assert lvl_count > 0, f"Expected entities for level {level} to be greater than 0"
            
        # Metrics verification
        metrics_count = session.query(MetricDaily).count()
        print(f"-> Total daily metric rows: {metrics_count}")
        assert metrics_count > 0, "Expected metrics daily rows to be greater than 0"
        
        # 3. Test Upsert behavior (Run sync again and verify no duplicate rows or key errors)
        print("\n[3] Running Sync Orchestrator again to verify UPSERT (overwrite) behavior...")
        # Running it again should update/replace the same key/date metrics and not duplicate
        orchestrator.sync(lookback_days=7)
        
        metrics_count_after = session.query(MetricDaily).count()
        print(f"-> Total daily metric rows after second sync: {metrics_count_after}")
        assert metrics_count == metrics_count_after, f"Upsert failed! Expected row count to remain {metrics_count}, but got {metrics_count_after}"
        print("-> Success! Row count remained identical. Upsert verified.")

        # 4. Run a query checking multi-provider integration
        print("\n[4] Querying combined metrics grouped by provider...")
        results = session.query(
            MetricDaily.provider,
            func.sum(MetricDaily.impressions).label("total_impressions"),
            func.sum(MetricDaily.clicks).label("total_clicks"),
            func.sum(MetricDaily.cost).label("total_cost"),
            func.sum(MetricDaily.conversions).label("total_conversions")
        ).group_by(MetricDaily.provider).all()
        
        for row in results:
            print(f"   - Provider: {row.provider.upper()}")
            print(f"     * Impressions: {row.total_impressions}")
            print(f"     * Clicks:      {row.total_clicks}")
            print(f"     * Cost:        {row.total_cost:.2f}")
            print(f"     * Conversions: {row.total_conversions:.2f}")
            
        print("\n=== VERIFICATION SUCCESSFUL ===")
    except Exception as e:
        print(f"\n!!! VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    verify()
