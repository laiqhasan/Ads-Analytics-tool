import calendar
import math
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session

def calculate_linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
    """
    Calculates the slope (m) and intercept (c) for the line of best fit y = mx + c.
    """
    n = len(x)
    if n < 2:
        return 0.0, 0.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    
    denominator = (n * sum_xx) - (sum_x * sum_x)
    if denominator == 0:
        return 0.0, 0.0
        
    m = (n * sum_xy - sum_x * sum_y) / denominator
    c = (sum_y - m * sum_x) / n
    return m, c

def project_monthly_spend(session: Session, account_id: str) -> dict:
    """
    Project month-end spend using both simple linear run-rate and cumulative linear trend regression.
    
    :param session: SQLAlchemy database session.
    :param account_id: Native account ID string.
    :return: A dictionary containing metrics and month-end projections.
    """
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    query = text("""
        SELECT date, SUM(cost) as daily_cost
        FROM metrics_daily
        WHERE account_id = :account_id AND date >= :start_of_month AND date <= :today
        GROUP BY date
        ORDER BY date ASC;
    """)
    rows = session.execute(query, {"account_id": account_id, "start_of_month": start_of_month, "today": today}).all()
    
    if not rows:
        return {
            "days_elapsed": 0,
            "total_days_in_month": calendar.monthrange(today.year, today.month)[1],
            "actual_mtd_spend": 0.0,
            "runrate_projection": 0.0,
            "linear_projection": 0.0
        }
        
    days_elapsed = len(rows)
    actual_mtd_spend = sum(float(r.daily_cost or 0.0) for r in rows)
    _, total_days = calendar.monthrange(today.year, today.month)
    
    # Run-rate projection: (mtd_spend / elapsed) * total_days
    runrate_projection = (actual_mtd_spend / days_elapsed) * total_days
    
    # Linear Regression projection: fits trend line over cumulative MTD daily spends
    x = []
    y = []
    cumulative = 0.0
    for idx, row in enumerate(rows, start=1):
        cumulative += float(row.daily_cost or 0.0)
        x.append(float(idx))
        y.append(cumulative)
        
    if days_elapsed >= 2:
        m, c = calculate_linear_regression(x, y)
        linear_projection = (m * total_days) + c
    else:
        linear_projection = runrate_projection
        
    return {
        "days_elapsed": days_elapsed,
        "total_days_in_month": total_days,
        "actual_mtd_spend": round(actual_mtd_spend, 2),
        "runrate_projection": round(runrate_projection, 2),
        "linear_projection": round(linear_projection, 2)
    }

def detect_anomalies(session: Session, account_id: str, metric: str = "cost", lookback_days: int = 14, z_threshold: float = 2.5) -> list:
    """
    Scan daily metrics for anomalies.
    Compares each daily aggregate against its trailing average/stddev window.
    
    :param session: SQLAlchemy database session.
    :param account_id: Native account ID string.
    :param metric: Target column name ('cost', 'clicks', 'impressions', 'conversions').
    :param lookback_days: Rolling window size (default 14 days) to calculate average/stddev.
    :param z_threshold: Critical threshold for anomaly flagging (default 2.5 standard deviations).
    :return: List of anomaly dict records containing the date, metric, value, and z-score.
    """
    query = text(f"""
        SELECT date, SUM({metric}) as metric_value
        FROM metrics_daily
        WHERE account_id = :account_id
        GROUP BY date
        ORDER BY date ASC;
    """)
    rows = session.execute(query, {"account_id": account_id}).all()
    
    if len(rows) <= lookback_days:
        return []
        
    anomalies = []
    values = [float(r.metric_value or 0.0) for r in rows]
    dates = [r.date for r in rows]
    
    for i in range(lookback_days, len(values)):
        window = values[i - lookback_days : i]
        mean = sum(window) / lookback_days
        variance = sum((x - mean) ** 2 for x in window) / lookback_days
        std_dev = math.sqrt(variance)
        
        current_value = values[i]
        z_score = 0.0
        if std_dev > 0:
            z_score = (current_value - mean) / std_dev
            
        if abs(z_score) > z_threshold:
            anomalies.append({
                "date": dates[i],
                "metric": metric,
                "value": round(current_value, 2),
                "expected_mean": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "z_score": round(z_score, 2),
                "severity": "high" if abs(z_score) > z_threshold * 1.5 else "medium"
            })
            
    return anomalies
