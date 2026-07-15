"""Add analysis views

Revision ID: afed2a44586f
Revises: 3a72552c6152
Create Date: 2026-07-15 14:39:45.950619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afed2a44586f'
down_revision: Union[str, Sequence[str], None] = '3a72552c6152'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create v_metrics_derived
    op.execute("""
        CREATE VIEW v_metrics_derived AS
        SELECT
            entity_key,
            provider,
            account_id,
            level,
            date,
            impressions,
            clicks,
            cost,
            conversions,
            conv_value,
            raw,
            synced_at,
            CASE 
                WHEN impressions > 0 THEN CAST(clicks AS FLOAT) / impressions 
                ELSE 0.0 
            END AS ctr,
            CASE 
                WHEN clicks > 0 THEN CAST(cost AS FLOAT) / clicks 
                ELSE 0.0 
            END AS cpc,
            CASE 
                WHEN conversions > 0 THEN CAST(cost AS FLOAT) / conversions 
                ELSE 0.0 
            END AS cpa,
            CASE 
                WHEN cost > 0 THEN CAST(conv_value AS FLOAT) / cost 
                ELSE 0.0 
            END AS roas
        FROM metrics_daily;
    """)

    # 2. Create v_wasted_spend
    op.execute("""
        CREATE VIEW v_wasted_spend AS
        SELECT
            entity_key,
            provider,
            account_id,
            date,
            impressions,
            clicks,
            cost,
            conversions,
            conv_value,
            raw
        FROM metrics_daily
        WHERE level = 'search_term' AND cost >= 50.0 AND conversions = 0.0;
    """)

    # 3. Create v_campaign_overall
    op.execute("""
        CREATE VIEW v_campaign_overall AS
        SELECT
            entity_key,
            provider,
            account_id,
            SUM(impressions) AS total_impressions,
            SUM(clicks) AS total_clicks,
            SUM(cost) AS total_cost,
            SUM(conversions) AS total_conversions,
            SUM(conv_value) AS total_conv_value,
            CASE 
                WHEN SUM(impressions) > 0 THEN CAST(SUM(clicks) AS FLOAT) / SUM(impressions) 
                ELSE 0.0 
            END AS ctr,
            CASE 
                WHEN SUM(clicks) > 0 THEN CAST(SUM(cost) AS FLOAT) / SUM(clicks) 
                ELSE 0.0 
            END AS cpc,
            CASE 
                WHEN SUM(conversions) > 0 THEN CAST(SUM(cost) AS FLOAT) / SUM(conversions) 
                ELSE 0.0 
            END AS cpa,
            CASE 
                WHEN SUM(cost) > 0 THEN CAST(SUM(conv_value) AS FLOAT) / SUM(cost) 
                ELSE 0.0 
            END AS roas
        FROM metrics_daily
        WHERE level = 'campaign'
        GROUP BY entity_key, provider, account_id;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_campaign_overall;")
    op.execute("DROP VIEW IF EXISTS v_wasted_spend;")
    op.execute("DROP VIEW IF EXISTS v_metrics_derived;")

