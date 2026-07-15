import calendar
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session

def get_wasted_spend(session: Session, min_cost: float = 50.0) -> list:
    """
    Find search terms with cost >= min_cost and 0 conversions.
    Queries the v_wasted_spend view.
    """
    query = text("""
        SELECT 
            w.entity_key,
            w.provider,
            w.account_id,
            w.date,
            w.cost,
            w.impressions,
            w.clicks,
            w.conversions,
            w.conv_value,
            e.name AS search_term_name
        FROM v_wasted_spend w
        JOIN entities e ON w.entity_key = e.entity_key
        WHERE w.cost >= :min_cost
        ORDER BY w.cost DESC;
    """)
    result = session.execute(query, {"min_cost": min_cost})
    return [dict(row._mapping) for row in result]

def get_budget_pacing(session: Session, account_budgets: dict[str, float]) -> list:
    """
    Check budget pacing for accounts.
    mtd_actual_spend is compared against expected linear pacing.
    
    :param account_budgets: Dict mapping account_id to monthly target budget (float).
    """
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    # Calculate pacing fraction
    _, total_days = calendar.monthrange(today.year, today.month)
    current_day = today.day
    pacing_fraction = current_day / total_days

    query = text("""
        SELECT 
            account_id,
            provider,
            SUM(cost) as mtd_spend
        FROM metrics_daily
        WHERE date >= :start_of_month AND date <= :today
        GROUP BY account_id, provider;
    """)
    result = session.execute(query, {"start_of_month": start_of_month, "today": today})
    
    pacing_reports = []
    for row in result:
        account_id = row.account_id
        provider = row.provider
        mtd_spend = float(row.mtd_spend or 0.0)
        
        # Get target budget (default to a mock $5000 if not specified)
        target_budget = account_budgets.get(account_id, 5000.0)
        expected_mtd_spend = target_budget * pacing_fraction
        
        deviation = 0.0
        if expected_mtd_spend > 0:
            deviation = (mtd_spend - expected_mtd_spend) / expected_mtd_spend
            
        status = "on_pace"
        if deviation > 0.15:
            status = "overspending"
        elif deviation < -0.15:
            status = "underspending"
            
        pacing_reports.append({
            "account_id": account_id,
            "provider": provider,
            "target_budget": target_budget,
            "expected_mtd_spend": round(expected_mtd_spend, 2),
            "actual_mtd_spend": round(mtd_spend, 2),
            "deviation_pct": round(deviation * 100, 2),
            "status": status
        })
        
    return pacing_reports

def get_underperforming_entities(session: Session, min_entity_cost: float = 50.0, multiplier: float = 2.0) -> list:
    """
    Find entities (campaigns, adgroups, ads) whose CPA is higher than their account's average CPA
    by the specified multiplier (e.g. > 2.0x average), with a minimum spend threshold.
    """
    # 1. Query overall account CPA (cost / conversions)
    account_cpa_query = text("""
        SELECT 
            account_id,
            SUM(cost) as total_cost,
            SUM(conversions) as total_conversions,
            CASE 
                WHEN SUM(conversions) > 0 THEN SUM(cost) / SUM(conversions) 
                ELSE 0.0 
            END as avg_account_cpa
        FROM metrics_daily
        GROUP BY account_id;
    """)
    account_cpas = {row.account_id: float(row.avg_account_cpa or 0.0) for row in session.execute(account_cpa_query)}
    
    # 2. Query entity CPA for level in campaign, adgroup, ad
    entity_cpa_query = text("""
        SELECT 
            m.entity_key,
            m.provider,
            m.account_id,
            m.level,
            e.name as entity_name,
            SUM(m.cost) as entity_cost,
            SUM(m.conversions) as entity_conversions,
            CASE 
                WHEN SUM(m.conversions) > 0 THEN SUM(m.cost) / SUM(m.conversions) 
                ELSE 0.0 
            END as entity_cpa
        FROM metrics_daily m
        JOIN entities e ON m.entity_key = e.entity_key
        WHERE m.level IN ('campaign', 'adgroup', 'ad')
        GROUP BY m.entity_key, m.provider, m.account_id, m.level, e.name
        HAVING SUM(m.cost) >= :min_entity_cost;
    """)
    
    underperformers = []
    entities_result = session.execute(entity_cpa_query, {"min_entity_cost": min_entity_cost})
    for row in entities_result:
        account_id = row.account_id
        avg_cpa = account_cpas.get(account_id, 0.0)
        entity_cpa = float(row.entity_cpa or 0.0)
        entity_cost = float(row.entity_cost or 0.0)
        
        is_underperforming = False
        reason = ""
        
        if avg_cpa > 0:
            if row.entity_conversions > 0 and entity_cpa > (avg_cpa * multiplier):
                is_underperforming = True
                reason = f"CPA ({entity_cpa:.2f}) is > {multiplier}x account average CPA ({avg_cpa:.2f})"
            elif row.entity_conversions == 0 and entity_cost > (avg_cpa * multiplier):
                is_underperforming = True
                reason = f"Spent {entity_cost:.2f} with 0 conversions (account average CPA is {avg_cpa:.2f})"
        
        if is_underperforming:
            underperformers.append({
                "entity_key": row.entity_key,
                "provider": row.provider,
                "account_id": account_id,
                "level": row.level,
                "entity_name": row.entity_name,
                "entity_cost": round(entity_cost, 2),
                "entity_conversions": float(row.entity_conversions),
                "entity_cpa": round(entity_cpa, 2),
                "account_avg_cpa": round(avg_cpa, 2),
                "reason": reason
            })
            
    return underperformers
