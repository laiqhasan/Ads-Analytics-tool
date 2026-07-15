import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from db.session import SessionLocal
from db.models import Entity
from analysis.tier1_rules import get_wasted_spend
from analysis.tier2_stats import detect_anomalies

logger = logging.getLogger(__name__)

def compare_periods(
    account_id: str, 
    level: str, 
    start_a: str, 
    end_a: str, 
    start_b: str, 
    end_b: str
) -> List[Dict[str, Any]]:
    """
    Compare performance metrics for an account/level between two date ranges (Period A vs Period B).
    
    :param account_id: Ad account ID.
    :param level: Entity level ('campaign', 'adgroup', 'ad', 'keyword', 'search_term').
    :param start_a: Start date of Period A (YYYY-MM-DD).
    :param end_a: End date of Period A (YYYY-MM-DD).
    :param start_b: Start date of Period B (YYYY-MM-DD).
    :param end_b: End date of Period B (YYYY-MM-DD).
    :return: A list of dicts with metrics and delta calculations for each entity.
    """
    logger.info(f"compare_periods called: account={account_id}, level={level}, period_a=[{start_a}, {end_a}], period_b=[{start_b}, {end_b}]")
    
    dt_start_a = datetime.strptime(start_a, "%Y-%m-%d").date()
    dt_end_a = datetime.strptime(end_a, "%Y-%m-%d").date()
    dt_start_b = datetime.strptime(start_b, "%Y-%m-%d").date()
    dt_end_b = datetime.strptime(end_b, "%Y-%m-%d").date()

    session = SessionLocal()
    try:
        # Fetch metrics for period A
        query_a = text("""
            SELECT entity_key, SUM(impressions) as impressions, SUM(clicks) as clicks, 
                   SUM(cost) as cost, SUM(conversions) as conversions, SUM(conv_value) as conv_value
            FROM metrics_daily
            WHERE account_id = :account_id AND level = :level AND date >= :start AND date <= :end
            GROUP BY entity_key;
        """)
        metrics_a = {
            r.entity_key: r 
            for r in session.execute(query_a, {"account_id": account_id, "level": level, "start": dt_start_a, "end": dt_end_a}).all()
        }

        # Fetch metrics for period B
        query_b = text("""
            SELECT entity_key, SUM(impressions) as impressions, SUM(clicks) as clicks, 
                   SUM(cost) as cost, SUM(conversions) as conversions, SUM(conv_value) as conv_value
            FROM metrics_daily
            WHERE account_id = :account_id AND level = :level AND date >= :start AND date <= :end
            GROUP BY entity_key;
        """)
        metrics_b = {
            r.entity_key: r 
            for r in session.execute(query_b, {"account_id": account_id, "level": level, "start": dt_start_b, "end": dt_end_b}).all()
        }

        # Fetch entity names
        all_keys = list(set(list(metrics_a.keys()) + list(metrics_b.keys())))
        entities = {
            e.entity_key: e.name 
            for e in session.query(Entity).filter(Entity.entity_key.in_(all_keys)).all()
        }

        comparison = []
        for key in all_keys:
            ma = metrics_a.get(key)
            mb = metrics_b.get(key)

            cost_a = float(ma.cost or 0.0) if ma else 0.0
            cost_b = float(mb.cost or 0.0) if mb else 0.0
            conv_a = float(ma.conversions or 0.0) if ma else 0.0
            conv_b = float(mb.conversions or 0.0) if mb else 0.0
            val_a = float(ma.conv_value or 0.0) if ma else 0.0
            val_b = float(mb.conv_value or 0.0) if mb else 0.0
            clicks_a = int(ma.clicks or 0) if ma else 0
            clicks_b = int(mb.clicks or 0) if mb else 0
            impr_a = int(ma.impressions or 0) if ma else 0
            impr_b = int(mb.impressions or 0) if mb else 0

            # CPA, CTR, ROAS
            cpa_a = cost_a / conv_a if conv_a > 0 else 0.0
            cpa_b = cost_b / conv_b if conv_b > 0 else 0.0
            roas_a = val_a / cost_a if cost_a > 0 else 0.0
            roas_b = val_b / cost_b if cost_b > 0 else 0.0

            comparison.append({
                "entity_key": key,
                "entity_name": entities.get(key, "Unknown"),
                "period_a": {
                    "cost": round(cost_a, 2), "clicks": clicks_a, "impressions": impr_a,
                    "conversions": round(conv_a, 2), "cpa": round(cpa_a, 2), "roas": round(roas_a, 2)
                },
                "period_b": {
                    "cost": round(cost_b, 2), "clicks": clicks_b, "impressions": impr_b,
                    "conversions": round(conv_b, 2), "cpa": round(cpa_b, 2), "roas": round(roas_b, 2)
                },
                "deltas": {
                    "cost_diff": round(cost_b - cost_a, 2),
                    "conversions_diff": round(conv_b - conv_a, 2),
                    "clicks_diff": clicks_b - clicks_a,
                    "roas_diff": round(roas_b - roas_a, 2)
                }
            })
        return comparison
    finally:
        session.close()

def top_movers(
    account_id: str, 
    level: str, 
    metric: str, 
    start_a: str, 
    end_a: str, 
    start_b: str, 
    end_b: str
) -> Dict[str, Any]:
    """
    Find entities at the given level that have the largest change in a metric between two periods.
    
    :param metric: Target metric to analyze ('cost', 'clicks', 'impressions', 'conversions', 'conv_value').
    """
    logger.info(f"top_movers called: account={account_id}, level={level}, metric={metric}")
    comparisons = compare_periods(account_id, level, start_a, end_a, start_b, end_b)
    
    # Sort comparisons based on selected metric difference
    def get_diff(item):
        if metric == "cost":
            return item["deltas"]["cost_diff"]
        elif metric == "conversions":
            return item["deltas"]["conversions_diff"]
        elif metric == "clicks":
            return item["deltas"]["clicks_diff"]
        elif metric == "roas":
            return item["deltas"]["roas_diff"]
        return 0.0
        
    sorted_items = sorted(comparisons, key=get_diff, reverse=True)
    
    # Filter gainers (positive diff) and losers (negative diff)
    top_gainers = [
        {"entity_name": x["entity_name"], "entity_key": x["entity_key"], "diff": get_diff(x)} 
        for x in sorted_items if get_diff(x) > 0
    ]
    top_losers = [
        {"entity_name": x["entity_name"], "entity_key": x["entity_key"], "diff": get_diff(x)} 
        for x in reversed(sorted_items) if get_diff(x) < 0
    ]
    
    return {
        "metric": metric,
        "top_gainers": top_gainers[:3],
        "top_losers": top_losers[:3]
    }

def run_anomaly_scan(account_id: str, metric: str = "cost", lookback_days: int = 10) -> List[Dict[str, Any]]:
    """
    Run rolling z-score anomaly detection for an account.
    """
    logger.info(f"run_anomaly_scan called: account={account_id}, metric={metric}")
    session = SessionLocal()
    try:
        # Convert date to string format for JSON serialization compatibility
        anomalies = detect_anomalies(session, account_id, metric, lookback_days)
        for a in anomalies:
            if isinstance(a["date"], (date, datetime)):
                a["date"] = a["date"].isoformat()
        return anomalies
    finally:
        session.close()

def wasted_spend(account_id: str, min_cost: float = 50.0) -> List[Dict[str, Any]]:
    """
    Find non-converting search terms with spend >= min_cost.
    """
    logger.info(f"wasted_spend called: account={account_id}, min_cost={min_cost}")
    session = SessionLocal()
    try:
        wasted = [w for w in get_wasted_spend(session, min_cost) if w["account_id"] == account_id]
        for w in wasted:
            if isinstance(w["date"], (date, datetime)):
                w["date"] = w["date"].isoformat()
        return wasted
    finally:
        session.close()
