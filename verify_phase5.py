import sys
from datetime import date, timedelta
from sqlalchemy import text
from db.session import SessionLocal
from db.models import Account, Entity, MetricDaily, AutomationProposal
from connectors.mock import MockConnector
from connectors.meta import MetaConnector
from sync.orchestrator import SyncOrchestrator
from automation.engine import generate_proposals, execute_approved_proposals

def run_verification():
    print("=== STARTING PHASE 5 AUTOMATION VERIFICATION ===")
    
    session = SessionLocal()
    try:
        # 1. Sync baseline data
        print("\n[1] Syncing baseline mock data for Google and Meta...")
        connectors = [
            MockConnector(provider_name="google"),
            MetaConnector() # Runs in mock fallback mode
        ]
        orchestrator = SyncOrchestrator(SessionLocal, connectors)
        orchestrator.sync(lookback_days=10)
        
        # 2. Inject anomalies to trigger rules
        print("\n[2] Injecting anomalies to trigger rules...")
        
        # Injected Wasted Search Term (Google)
        st = session.query(Entity).filter_by(level="search_term", provider="google").first()
        if st:
            print(f"   -> Injecting Google wasted search term spend on: '{st.name}'")
            wasted_metric = MetricDaily(
                entity_key=st.entity_key,
                provider=st.provider,
                account_id=st.account_id,
                level="search_term",
                date=date.today() - timedelta(days=1),
                impressions=1200,
                clicks=90,
                cost=135.50,  # exceeds $50 threshold
                conversions=0.0,
                conv_value=0.0
            )
            session.merge(wasted_metric)
            
        # Injected CPA Underperformer (Meta Ad)
        ad_entity = session.query(Entity).filter_by(level="ad", provider="meta").first()
        if ad_entity:
            print(f"   -> Injecting Meta underperforming CPA on ad: '{ad_entity.name}'")
            # We inject high spend with 0 conversions compared to other ads
            metric = MetricDaily(
                entity_key=ad_entity.entity_key,
                provider=ad_entity.provider,
                account_id=ad_entity.account_id,
                level="ad",
                date=date.today() - timedelta(days=1),
                impressions=3000,
                clicks=300,
                cost=2500.00,  # very high cost
                conversions=0.0,  # 0 conversions to maximize CPA deviation
                conv_value=0.0
            )
            session.merge(metric)
            
        session.commit()
        
        # 3. Generate Proposals
        print("\n[3] Generating proposals based on analysis diagnostics...")
        created_count = generate_proposals(session)
        print(f"   -> Created {created_count} proposals.")
        assert created_count >= 2, f"Expected at least 2 proposals (1 Google negative keyword + 1 Meta CPA pause), got {created_count}"
        
        # Inspect created proposals
        proposals = session.query(AutomationProposal).all()
        for p in proposals:
            print(f"      * Proposal ID={p.id} | Provider={p.provider.upper()} | Action={p.action_type} | Status={p.status} | Reason='{p.reason}'")
            
        # 4. Human-in-the-loop Approval Simulation
        print("\n[4] Simulating approval of Google negative keyword proposal...")
        google_prop = session.query(AutomationProposal).filter_by(provider="google", action_type="add_negative_keyword").first()
        assert google_prop is not None, "Expected a Google negative keyword proposal to exist"
        google_prop.status = "approved"
        session.commit()
        print(f"   -> Approved Proposal ID: {google_prop.id} for term '{google_prop.details['keyword']}'")
        
        # 5. Execute Approved Proposals
        print("\n[5] Executing approved proposals through the dispatch pipeline...")
        executed_count = execute_approved_proposals(session, connectors)
        print(f"   -> Successfully executed {executed_count} proposals.")
        assert executed_count == 1, f"Expected 1 executed proposal, got {executed_count}"
        
        # 6. Verify Post-Execution States
        print("\n[6] Auditing proposal statuses after execution...")
        session.expire_all()
        
        p_google = session.query(AutomationProposal).filter_by(id=google_prop.id).first()
        print(f"      * Google Proposal ID={p_google.id} status is now: {p_google.status.upper()}")
        assert p_google.status == "executed", f"Expected Google proposal to be EXECUTED, got {p_google.status}"
        
        p_meta = session.query(AutomationProposal).filter_by(provider="meta").first()
        print(f"      * Meta Proposal ID={p_meta.id} status remains: {p_meta.status.upper()}")
        assert p_meta.status == "pending", f"Expected Meta proposal to remain PENDING, got {p_meta.status}"
        
        print("\n=== PHASE 5 AUTOMATION VERIFICATION SUCCESSFUL ===")
    except Exception as e:
        print(f"\n!!! PHASE 5 AUTOMATION VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_verification()
