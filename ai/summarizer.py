import logging
from sqlalchemy.orm import Session
from ai.router import generate_text
from analysis.tier1_rules import get_wasted_spend, get_budget_pacing, get_underperforming_entities
from analysis.tier2_stats import project_monthly_spend, detect_anomalies
from db.models import Account

logger = logging.getLogger(__name__)

def generate_account_summary(session: Session, account_id: str, monthly_budget: float = 5000.0) -> str:
    """
    Generates a daily plain-English narrative performance summary for a client ad account.
    Funnels Tier 1 rules and Tier 2 statistics into a grounded LLM prompt.
    
    :param session: SQLAlchemy database session.
    :param account_id: Ad account ID.
    :param monthly_budget: Target monthly budget for pacing checks.
    :return: A markdown formatted string summary.
    """
    # 1. Fetch Account info
    acc = session.query(Account).filter_by(account_id=account_id).first()
    client_name = acc.client_name if acc else "Unknown Client"
    provider = acc.provider.upper() if acc else "UNKNOWN"
    
    # 2. Gather diagnostics
    wasted = [w for w in get_wasted_spend(session, min_cost=50.0) if w["account_id"] == account_id]
    pacing_list = get_budget_pacing(session, account_budgets={account_id: monthly_budget})
    pacing = pacing_list[0] if pacing_list else None
    underperformers = [u for u in get_underperforming_entities(session, min_entity_cost=50.0) if u["account_id"] == account_id]
    forecast = project_monthly_spend(session, account_id)
    anomalies = detect_anomalies(session, account_id, metric="cost", lookback_days=10)
    
    # 3. Build diagnostic text payload
    diagnostics = f"Account Name: {client_name}\n"
    diagnostics += f"Account ID: {account_id}\n"
    diagnostics += f"Provider: {provider}\n\n"
    
    if pacing:
        diagnostics += "--- BUDGET PACING ---\n"
        diagnostics += f"Monthly Target Budget: ${pacing['target_budget']:.2f}\n"
        diagnostics += f"MTD Actual Spend: ${pacing['actual_mtd_spend']:.2f}\n"
        diagnostics += f"MTD Expected Spend: ${pacing['expected_mtd_spend']:.2f}\n"
        diagnostics += f"Deviation: {pacing['deviation_pct']}%\n"
        diagnostics += f"Pacing Status: {pacing['status'].upper()}\n\n"
        
    diagnostics += "--- FORECASTING ---\n"
    diagnostics += f"Run-rate Projected Spend: ${forecast['runrate_projection']:.2f}\n"
    diagnostics += f"Linear Regression Trend Projected Spend: ${forecast['linear_projection']:.2f}\n\n"
    
    diagnostics += "--- WASTED SPEND ALERTS (Spent >= $50 with 0 conversions) ---\n"
    if wasted:
        for idx, w in enumerate(wasted, start=1):
            diagnostics += f"{idx}. Search term '{w['search_term_name']}' spent ${w['cost']:.2f} with 0 conversions ({w['clicks']} clicks, {w['impressions']} impressions)\n"
    else:
        diagnostics += "No wasted spend search terms flagged.\n"
    diagnostics += "\n"
        
    diagnostics += "--- UNDERPERFORMING CPA ENTITIES (CPA > 2.0x Account Average) ---\n"
    if underperformers:
        for idx, u in enumerate(underperformers, start=1):
            diagnostics += f"{idx}. {u['level'].upper()} '{u['entity_name']}' spent ${u['entity_cost']:.2f} with CPA ${u['entity_cpa']:.2f} (Account Avg: ${u['account_avg_cpa']:.2f}) - Reason: {u['reason']}\n"
    else:
        diagnostics += "No CPA underperforming campaigns, ad groups, or ads flagged.\n"
    diagnostics += "\n"
    
    diagnostics += "--- DAILY COST ANOMALIES DETECTED ---\n"
    if anomalies:
        for idx, a in enumerate(anomalies, start=1):
            diagnostics += f"{idx}. Date: {a['date']} | Value: ${a['value']:.2f} | Expected Trailing Mean: ${a['expected_mean']:.2f} | Z-Score: {a['z_score']} ({a['severity'].upper()} severity)\n"
    else:
        diagnostics += "No rolling standard deviation anomalies detected.\n"
        
    # 4. Generate prompt
    system_instruction = (
        "You are an expert digital marketing analyst writing performance executive summaries for agency clients. "
        "Your summaries must be concise, professional, plain-English, and action-oriented. "
        "Strict Rule: NEVER invent or hallucinate any metrics. Only discuss the data explicitly provided."
    )
    
    prompt = (
        f"Please write a short narrative performance summary for client '{client_name}' based on the following diagnostic data:\n\n"
        f"{diagnostics}\n"
        "Format your response with standard markdown headers. Focus on highlighting major issues (like pacing, cost spikes, and wasted budget search terms) and provide clear recommendations."
    )
    
    logger.info(f"Generating narrative summary for account {account_id}")
    summary = generate_text(prompt=prompt, model_type="flash", system_instruction=system_instruction)
    return summary
