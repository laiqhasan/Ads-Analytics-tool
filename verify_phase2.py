import sys
from datetime import date, timedelta
from sqlalchemy import text
from db.session import SessionLocal
from db.models import Entity, MetricDaily
from connectors.mock import MockConnector
from sync.orchestrator import SyncOrchestrator
from analysis.tier1_rules import get_wasted_spend, get_budget_pacing, get_underperforming_entities
from analysis.tier2_stats import project_monthly_spend, detect_anomalies

def run_verification():
    print("=== STARTING PHASE 2 VERIFICATION ===")
    
    # 1. Sync baseline data
    print("\n[1] Syncing baseline mock data...")
    connectors = [MockConnector(provider_name="google")]
    orchestrator = SyncOrchestrator(SessionLocal, connectors)
    # Sync a 20-day window to provide enough history for rolling statistics
    orchestrator.sync(lookback_days=20)
    
    session = SessionLocal()
    try:
        # 2. Inject test anomalies
        print("\n[2] Injecting test data anomalies into SQLite...")
        
        # Injected Wasted Spend Search Term:
        # We find one of the synced search terms and set its cost to $120.0 and conversions to 0
        search_term_entity = session.query(Entity).filter_by(level="search_term").first()
        if search_term_entity:
            print(f"   -> Injecting wasted spend on search term: {search_term_entity.name}")
            wasted_metric = MetricDaily(
                entity_key=search_term_entity.entity_key,
                provider=search_term_entity.provider,
                account_id=search_term_entity.account_id,
                level="search_term",
                date=date.today() - timedelta(days=1),
                impressions=1000,
                clicks=80,
                cost=120.0,  # > $50 threshold
                conversions=0.0,
                conv_value=0.0
            )
            session.merge(wasted_metric)
            
        # Injected Cost Anomaly:
        # We inject a massive cost spike on today for a campaign in account '123-456-7890'
        campaign_entity = session.query(Entity).filter_by(level="campaign", account_id="123-456-7890").first()
        if campaign_entity:
            print(f"   -> Injecting a massive cost spike on campaign: {campaign_entity.name}")
            anomaly_metric = MetricDaily(
                entity_key=campaign_entity.entity_key,
                provider=campaign_entity.provider,
                account_id=campaign_entity.account_id,
                level="campaign",
                date=date.today(),
                impressions=5000,
                clicks=800,
                cost=1800.0,  # massive spike compared to normal ~$100-$300
                conversions=2.0,
                conv_value=40.0
            )
            session.merge(anomaly_metric)
            
        session.commit()
        
        # 3. Query derived SQL views
        print("\n[3] Querying derived SQL database views...")
        derived_rows = session.execute(text("SELECT entity_key, date, ctr, cpc, cpa, roas FROM v_metrics_derived LIMIT 3;")).all()
        print("   -> Samples from v_metrics_derived:")
        for r in derived_rows:
            print(f"      Key={r.entity_key} | Date={r.date} | CTR={r.ctr:.4f} | CPC=${r.cpc:.2f} | CPA=${r.cpa:.2f} | ROAS={r.roas:.2f}")
            
        campaign_overall = session.execute(text("SELECT entity_key, total_cost, roas FROM v_campaign_overall LIMIT 2;")).all()
        print("   -> Samples from v_campaign_overall:")
        for r in campaign_overall:
            print(f"      Key={r.entity_key} | Total Cost=${r.total_cost:.2f} | ROAS={r.roas:.2f}")
            
        # 4. Validate Tier 1 Rules
        print("\n[4] Running Tier 1 SQL Rules Engine...")
        
        # Wasted spend
        wasted = get_wasted_spend(session, min_cost=50.0)
        print(f"   -> Wasted spend terms count: {len(wasted)}")
        for w in wasted[:3]:
            print(f"      * Term: '{w['search_term_name']}' | Cost: ${w['cost']:.2f} | Conversions: {w['conversions']}")
        assert len(wasted) >= 1, "Expected at least 1 wasted search term to be caught"
        
        # Budget Pacing (assuming $6000.0 budget for '123-456-7890' to simulate overspending due to cost spike)
        budgets = {"123-456-7890": 6000.0}
        pacing = get_budget_pacing(session, account_budgets=budgets)
        for p in pacing:
            print(f"      * Account: {p['account_id']} | MTD Spend: ${p['actual_mtd_spend']:.2f} | Target: ${p['target_budget']:.2f} | Status: {p['status'].upper()} ({p['deviation_pct']}% dev)")
            
        # CPA Underperformers
        underperformers = get_underperforming_entities(session, min_entity_cost=50.0, multiplier=2.0)
        print(f"   -> CPA Underperforming entities count: {len(underperformers)}")
        for u in underperformers[:3]:
            print(f"      * Entity: '{u['entity_name']}' ({u['level'].upper()}) | Cost: ${u['entity_cost']:.2f} | CPA: ${u['entity_cpa']:.2f} (Account Avg: ${u['account_avg_cpa']:.2f})")
            
        # 5. Validate Tier 2 Statistics
        print("\n[5] Running Tier 2 Statistics Engine...")
        
        # Forecasting
        forecast = project_monthly_spend(session, account_id="123-456-7890")
        print(f"   -> Monthly Spend Forecast for Account 123-456-7890:")
        print(f"      * Actual MTD Spend: ${forecast['actual_mtd_spend']:.2f} ({forecast['days_elapsed']} days elapsed)")
        print(f"      * Run-Rate Projection: ${forecast['runrate_projection']:.2f}")
        print(f"      * Linear Regression Projection: ${forecast['linear_projection']:.2f}")
        
        # Anomaly detection
        anomalies = detect_anomalies(session, account_id="123-456-7890", metric="cost", lookback_days=10, z_threshold=2.2)
        print(f"   -> Cost anomalies detected count: {len(anomalies)}")
        for a in anomalies:
            print(f"      * Date: {a['date']} | Value: ${a['value']:.2f} | Expected Mean: ${a['expected_mean']:.2f} | Z-Score: {a['z_score']} | Severity: {a['severity'].upper()}")
        assert len(anomalies) >= 1, "Expected the injected cost spike to be flagged as an anomaly"
        
        print("\n=== PHASE 2 VERIFICATION SUCCESSFUL ===")
    except Exception as e:
        print(f"\n!!! PHASE 2 VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    run_verification()
