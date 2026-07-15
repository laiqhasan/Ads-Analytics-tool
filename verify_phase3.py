import sys
from db.session import SessionLocal
from ai.summarizer import generate_account_summary
from ai.agent import run_agent_query
from ai.copy_generator import generate_rsa_copy

def verify_ai_layer():
    print("=== STARTING PHASE 3 AI LAYER VERIFICATION ===")
    
    session = SessionLocal()
    try:
        # 1. Verify Summarizer (Tier 3)
        print("\n[1] Running Summarizer (Tier 3) Narrative generation...")
        summary = generate_account_summary(session, account_id="123-456-7890")
        print("   -> Generated Narrative Summary output:")
        print("-" * 50)
        print(summary)
        print("-" * 50)
        assert len(summary) > 0, "Summary should not be empty"
        
        # 2. Verify Agentic Investigation (Tier 4)
        print("\n[2] Running Agentic Investigation (Tier 4) for ROAS/conversions drop query...")
        query = "Why did campaign conversions and ROAS drop last week?"
        agent_report = run_agent_query(user_query=query, account_id="123-456-7890")
        print("   -> Generated Agent Report output:")
        print("-" * 50)
        print(agent_report)
        print("-" * 50)
        assert len(agent_report) > 0, "Agent report should not be empty"
        assert "Agent Reasoning Trace" in agent_report, "Agent report should contain a reasoning trace"
        
        # 3. Verify Ad-Copy Generator (with length constraints)
        print("\n[3] Running Ad-Copy Generator and validating RSA constraints...")
        rsa_copy = generate_rsa_copy(session, account_id="123-456-7890")
        
        print(f"   -> Generated {len(rsa_copy['headlines'])} Headlines:")
        for idx, h in enumerate(rsa_copy["headlines"], start=1):
            print(f"      * {idx}. {h} (len={len(h)})")
            assert len(h) <= 30, f"Headline '{h}' exceeded 30 character limit! (len={len(h)})"
            
        print(f"   -> Generated {len(rsa_copy['descriptions'])} Descriptions:")
        for idx, d in enumerate(rsa_copy["descriptions"], start=1):
            print(f"      * {idx}. {d} (len={len(d)})")
            assert len(d) <= 90, f"Description '{d}' exceeded 90 character limit! (len={len(d)})"
            
        assert len(rsa_copy["headlines"]) > 0, "Should generate at least one headline"
        assert len(rsa_copy["descriptions"]) > 0, "Should generate at least one description"
        
        print("\n=== PHASE 3 AI LAYER VERIFICATION SUCCESSFUL ===")
    except Exception as e:
        print(f"\n!!! PHASE 3 AI LAYER VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    verify_ai_layer()
