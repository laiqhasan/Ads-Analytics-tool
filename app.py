import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import threading
from datetime import date, timedelta
from sqlalchemy import text
from db.session import SessionLocal
from db.models import Account, Entity, MetricDaily, AutomationProposal
from sync.orchestrator import SyncOrchestrator
from connectors.mock import MockConnector
from connectors.meta import MetaConnector
from scheduler import run_loop as start_scheduler_loop
from analysis.tier1_rules import get_budget_pacing, get_wasted_spend, get_underperforming_entities
from analysis.tier2_stats import detect_anomalies, project_monthly_spend
from ai.agent import run_agent_query
from automation.engine import execute_approved_proposals

# Set up Streamlit Page Configuration with Sleek Icons and Wide Layout
st.set_page_config(
    page_title="Ads Analytics Console",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Start background sync scheduler loop in a background thread on web startup
@st.cache_resource
def init_background_scheduler():
    # Pass start_web_server=False to avoid port conflicts
    t = threading.Thread(target=start_scheduler_loop, args=(False,), daemon=True)
    t.start()
    return True

init_background_scheduler()

# DB Helper functions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper to parse reasoning trace from Gemini
def parse_agent_response(result: str):
    if "### Agent Reasoning Trace:" in result:
        sub = result.split("### Agent Reasoning Trace:\n")[-1]
        if "### Executive Agent Investigation Report" in sub:
            trace_part, report_part = sub.split("### Executive Agent Investigation Report")
            return trace_part.strip(), "### Executive Agent Investigation Report" + report_part
        else:
            blocks = sub.split("\n\n")
            if len(blocks) > 1:
                trace_part = "\n\n".join(blocks[:-1])
                report_part = blocks[-1]
                return trace_part.strip(), report_part.strip()
    return None, result

# Sidebar Configuration
st.sidebar.markdown("# 📊 Paid Ads Console")
st.sidebar.markdown("---")

# Query active accounts for selector
db = SessionLocal()
accounts = db.query(Account).all()
db.close()

if not accounts:
    st.sidebar.warning("No ad accounts synced. Trigger a sync job to populate the database.")
    selected_account = None
else:
    account_options = {f"{a.client_name} ({a.provider.upper()})": a for a in accounts}
    selected_acc_label = st.sidebar.selectbox("Select Account Scope", list(account_options.keys()))
    selected_account = account_options[selected_acc_label]

# Trigger manual sync from the UI
st.sidebar.markdown("### Actions")
if st.sidebar.button("Force Platform Sync Now"):
    with st.sidebar.spinner("Syncing platform API metrics..."):
        try:
            connectors = [MockConnector(provider_name="google"), MetaConnector()]
            orchestrator = SyncOrchestrator(SessionLocal, connectors)
            orchestrator.sync(lookback_days=14)
            st.sidebar.success("Sync completed! Refreshing page...")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Sync failed: {e}")

# Page Navigation Router
page = st.sidebar.radio(
    "Navigation Console",
    ["Overview Dashboard", "Diagnostics & Projections", "Confirmation Gate (Proposals)", "AI Analytics Assistant"]
)

# ----------------- OVERVIEW DASHBOARD PAGE -----------------
if page == "Overview Dashboard":
    st.title("Performance Overview Dashboard")
    
    if not selected_account:
        st.info("Please sync an account first to view details.")
    else:
        st.markdown(f"#### Account: `{selected_account.client_name}` | Provider: **{selected_account.provider.upper()}** | Currency: `{selected_account.currency}`")
        st.markdown("---")
        
        # 1. Date Range Picker
        col_dr1, col_dr2 = st.columns([1, 4])
        with col_dr1:
            date_range = st.selectbox("Date Window", ["Trailing 7 Days", "Trailing 30 Days", "Trailing 90 Days"], index=1)
        
        days_map = {"Trailing 7 Days": 7, "Trailing 30 Days": 30, "Trailing 90 Days": 90}
        days_lookback = days_map[date_range]
        start_date = date.today() - timedelta(days=days_lookback)
        
        # 2. Query Metrics
        db = SessionLocal()
        metrics_query = text("""
            SELECT 
                date,
                SUM(impressions) as impressions,
                SUM(clicks) as clicks,
                SUM(cost) as cost,
                SUM(conversions) as conversions,
                SUM(conv_value) as conv_value
            FROM metrics_daily
            WHERE account_id = :acc_id AND date >= :start_date
            GROUP BY date
            ORDER BY date ASC;
        """)
        df_daily = pd.read_sql_query(metrics_query, db.bind, params={"acc_id": selected_account.account_id, "start_date": start_date})
        db.close()
        
        if df_daily.empty:
            st.warning("No daily metrics found for this account in the selected date window.")
        else:
            # Aggregate KPIs
            total_spend = df_daily["cost"].sum()
            total_impr = df_daily["impressions"].sum()
            total_clicks = df_daily["clicks"].sum()
            total_conv = df_daily["conversions"].sum()
            total_value = df_daily["conv_value"].sum()
            
            cpc = total_spend / total_clicks if total_clicks > 0 else 0.0
            ctr = (total_clicks / total_impr) * 100 if total_impr > 0 else 0.0
            cpa = total_spend / total_conv if total_conv > 0 else 0.0
            roas = total_value / total_spend if total_spend > 0 else 0.0
            
            # Draw KPI Cards
            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            kpi1.metric("Spend", f"${total_spend:,.2f}")
            kpi2.metric("Clicks", f"{total_clicks:,}", f"{ctr:.2f}% CTR")
            kpi3.metric("CPC", f"${cpc:.2f}")
            kpi4.metric("Conversions", f"{total_conv:,.1f}", f"${cpa:.2f} CPA")
            kpi5.metric("ROAS", f"{roas:.2f}x", f"${total_value:,.2f} Value")
            
            st.markdown("### Performance Trends")
            
            # Draw Trend Chart
            fig = make_subplots = go.Figure()
            fig.add_trace(go.Bar(x=df_daily["date"], y=df_daily["cost"], name="Daily Cost", marker_color="#4F46E5", yaxis="y"))
            fig.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["conversions"], name="Conversions", line=dict(color="#10B981", width=3), yaxis="y2"))
            
            fig.update_layout(
                title="Daily Spend vs. Conversions Trend",
                yaxis=dict(title="Spend ($)", titlefont=dict(color="#4F46E5"), tickfont=dict(color="#4F46E5")),
                yaxis2=dict(title="Conversions", titlefont=dict(color="#10B981"), tickfont=dict(color="#10B981"), anchor="x", overlaying="y", side="right"),
                legend=dict(x=0.01, y=0.99),
                hovermode="x unified",
                template="plotly_dark"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Entity Breakdown Section
            st.markdown("### Entity Breakdown")
            db = SessionLocal()
            entity_breakdown_query = text("""
                SELECT 
                    e.level,
                    e.name,
                    SUM(m.cost) as spend,
                    SUM(m.clicks) as clicks,
                    SUM(m.conversions) as conversions,
                    CASE WHEN SUM(m.clicks) > 0 THEN SUM(m.cost) / SUM(m.clicks) ELSE 0.0 END as cpc,
                    CASE WHEN SUM(m.conversions) > 0 THEN SUM(m.cost) / SUM(m.conversions) ELSE 0.0 END as cpa,
                    CASE WHEN SUM(m.cost) > 0 THEN SUM(m.conv_value) / SUM(m.cost) ELSE 0.0 END as roas
                FROM metrics_daily m
                JOIN entities e ON m.entity_key = e.entity_key
                WHERE m.account_id = :acc_id AND m.date >= :start_date
                GROUP BY e.level, e.name
                ORDER BY spend DESC;
            """)
            df_entities = pd.read_sql_query(entity_breakdown_query, db.bind, params={"acc_id": selected_account.account_id, "start_date": start_date})
            db.close()
            
            level_select = st.selectbox("Filter Level Breakdown", ["campaign", "adgroup", "ad", "keyword", "search_term"])
            df_filtered = df_entities[df_entities["level"] == level_select]
            
            if df_filtered.empty:
                st.info(f"No metrics recorded at the '{level_select}' level for this date window.")
            else:
                st.dataframe(
                    df_filtered.drop(columns=["level"]).style.format({
                        "spend": "${:,.2f}",
                        "cpc": "${:,.2f}",
                        "cpa": "${:,.2f}",
                        "conversions": "{:,.1f}",
                        "roas": "{:.2f}x"
                    }),
                    use_container_width=True
                )

# ----------------- DIAGNOSTICS & PROJECTIONS PAGE -----------------
elif page == "Diagnostics & Projections":
    st.title("Diagnostics & Spend Projections")
    
    if not selected_account:
        st.info("Please sync an account first.")
    else:
        st.markdown(f"#### Account: `{selected_account.client_name}`")
        st.markdown("---")
        
        db = SessionLocal()
        
        # 1. Budget Pacing Diagnostic
        st.subheader("Monthly Budget Pacing")
        pacing_data = get_budget_pacing(db)
        # Filter for current account
        acc_pacing = [p for p in pacing_data if p["account_id"] == selected_account.account_id]
        if not acc_pacing:
            st.info("No pacing metrics computed for this account. Set campaign budgets to track pacing.")
        else:
            p = acc_pacing[0]
            pct = min(p["pace_percent"], 1.0)
            st.progress(pct)
            st.markdown(
                f"   * **MTD Spend**: ${p['mtd_spend']:.2f} / Target: ${p['mtd_target_budget']:.2f} "
                f"({p['pace_percent']*100:.1f}% paced)\n"
                f"   * **Status**: **{p['status'].upper()}** (Pacing Alert: {p['pacing_status']})"
            )
            
        # 2. Spend Projection Regression
        st.subheader("Spend Projection (Regression Model)")
        proj = project_monthly_spend(db, selected_account.account_id)
        if proj:
            col_pr1, col_pr2, col_pr3 = st.columns(3)
            col_pr1.metric("MTD Current Spend", f"${proj['current_spend']:,.2f}")
            col_pr2.metric("Projected Month-End (Run Rate)", f"${proj['run_rate_projection']:,.2f}")
            col_pr3.metric("Projected Month-End (Regression)", f"${proj['regression_projection']:,.2f}")
            
            # Plot projection line
            days = list(range(1, proj["days_in_month"] + 1))
            cum_spend_actual = proj["actual_cumulative"]
            regression_line = [proj["slope"] * d + proj["intercept"] for d in days]
            
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=days[:len(cum_spend_actual)], y=cum_spend_actual, name="Actual Spend", mode="lines+markers", line=dict(color="#4F46E5", width=3)))
            fig_proj.add_trace(go.Scatter(x=days, y=regression_line, name="Regression Projection Model", line=dict(color="#F59E0B", dash="dash")))
            
            fig_proj.update_layout(
                title="Cumulative Spend vs. Regression Trend",
                xaxis_title="Day of Month",
                yaxis_title="Spend ($)",
                template="plotly_dark"
            )
            st.plotly_chart(fig_proj, use_container_width=True)
            
        # 3. Wasted Search Terms
        st.subheader("Wasted Search Term Diagnostics")
        wasted_terms = get_wasted_spend(db, min_cost=50.0)
        acc_wasted = [w for w in wasted_terms if w["account_id"] == selected_account.account_id]
        
        if not acc_wasted:
            st.success("No wasted search terms detected. Excellent efficiency!")
        else:
            st.warning(f"Detected {len(acc_wasted)} search terms with > $50.00 spent and 0 conversions.")
            for w in acc_wasted:
                with st.container():
                    col_ws1, col_ws2 = st.columns([4, 1])
                    col_ws1.markdown(f"**Term**: `{w['search_term_name']}` | Cost: **${w['cost']:.2f}** | Clicks: `{w['clicks']}`")
                    
                    # Propose Action button
                    if col_ws2.button("Propose Block", key=f"ws_{w['entity_key']}"):
                        # Create Proposal
                        details = {"campaign_id": w["entity_key"].split(":")[-3], "keyword": w["search_term_name"]}
                        prop = AutomationProposal(
                            provider=selected_account.provider,
                            account_id=selected_account.account_id,
                            action_type="add_negative_keyword",
                            target_entity_key=w["entity_key"],
                            details=details,
                            status="pending",
                            reason=f"Wasted spend alert: spent ${w['cost']:.2f} with 0 conversions."
                        )
                        db.add(prop)
                        db.commit()
                        st.success(f"Proposed negative keyword block for '{w['search_term_name']}'!")
                        st.rerun()
                        
        # 4. Underperforming CPA Entities
        st.subheader("CPA Underperformers Alert")
        underperformers = get_underperforming_entities(db, min_entity_cost=50.0)
        acc_under = [u for u in underperformers if u["account_id"] == selected_account.account_id]
        
        if not acc_under:
            st.success("No high-CPA underperforming adgroups or ads detected.")
        else:
            for u in acc_under:
                with st.container():
                    col_un1, col_un2 = st.columns([4, 1])
                    col_un1.markdown(
                        f"**{u['level'].upper()}**: `{u['entity_name']}` | "
                        f"CPA: **${u['entity_cpa']:.2f}** vs. Avg Account CPA: `${u['account_avg_cpa']:.2f}`"
                    )
                    if col_un2.button("Propose Pause", key=f"un_{u['entity_key']}"):
                        details = {"level": u["level"], "native_id": u["entity_key"].split(":")[-1]}
                        prop = AutomationProposal(
                            provider=selected_account.provider,
                            account_id=selected_account.account_id,
                            action_type="pause_entity",
                            target_entity_key=u["entity_key"],
                            details=details,
                            status="pending",
                            reason=f"CPA alert: Entity CPA (${u['entity_cpa']:.2f}) is > 2.0x average (${u['account_avg_cpa']:.2f})."
                        )
                        db.add(prop)
                        db.commit()
                        st.success(f"Proposed pause for {u['level']} '{u['entity_name']}'!")
                        st.rerun()
                        
        # 5. Anomalies
        st.subheader("Daily Cost & Conversion Anomalies")
        anoms = detect_anomalies(db, z_threshold=2.0)
        acc_anoms = [a for a in anoms if a["account_id"] == selected_account.account_id]
        
        if not acc_anoms:
            st.success("No performance anomalies detected.")
        else:
            df_anoms = pd.DataFrame(acc_anoms)
            st.dataframe(
                df_anoms[["date", "level", "entity_name", "metric", "actual_value", "z_score", "anomaly_severity"]].style.format({
                    "actual_value": "{:.2f}",
                    "z_score": "{:.2f}"
                }),
                use_container_width=True
            )
            
        db.close()

# ----------------- CONFIRMATION GATE (PROPOSALS) PAGE -----------------
elif page == "Confirmation Gate (Proposals)":
    st.title("Human-In-The-Loop Confirmation Gate")
    st.markdown("Verify and approve proposed performance actions before they are executed on ad platforms.")
    st.markdown("---")
    
    db = SessionLocal()
    
    # Query proposals
    pending = db.query(AutomationProposal).filter_by(status="pending").all()
    history = db.query(AutomationProposal).filter(AutomationProposal.status.in_(["executed", "rejected", "failed"])).all()
    
    tab1, tab2 = st.tabs(["Pending Approvals", "Execution History"])
    
    with tab1:
        if not pending:
            st.success("No pending automation proposals. Check Diagnostics to trigger rules.")
        else:
            for p in pending:
                with st.expander(f"Proposal ID {p.id}: {p.action_type.replace('_', ' ').title()} ({p.provider.upper()})", expanded=True):
                    col_p1, col_p2 = st.columns([4, 1])
                    with col_p1:
                        st.markdown(f"**Target Entity Key**: `{p.target_entity_key}`")
                        st.markdown(f"**Reason**: *{p.reason}*")
                        st.json(p.details)
                    with col_p2:
                        if st.button("Approve & Exec", key=f"app_{p.id}", use_container_width=True):
                            p.status = "approved"
                            db.commit()
                            
                            # Execute immediately
                            with st.spinner("Dispatching API write operation..."):
                                connectors = [MockConnector(provider_name="google"), MetaConnector()]
                                executed_cnt = execute_approved_proposals(db, connectors)
                                if executed_cnt > 0:
                                    st.success(f"Proposal {p.id} executed successfully!")
                                else:
                                    st.error(f"Proposal {p.id} execution failed. Check logs.")
                            st.rerun()
                            
                        if st.button("Reject", key=f"rej_{p.id}", use_container_width=True):
                            p.status = "rejected"
                            db.commit()
                            st.info(f"Proposal {p.id} rejected.")
                            st.rerun()
                            
    with tab2:
        if not history:
            st.info("No proposal history available.")
        else:
            hist_records = []
            for h in history:
                hist_records.append({
                    "ID": h.id,
                    "Provider": h.provider.upper(),
                    "Account": h.account_id,
                    "Action": h.action_type,
                    "Status": h.status.upper(),
                    "Reason": h.reason,
                    "Created": h.created_at.strftime("%Y-%m-%d %H:%M") if h.created_at else None,
                    "Reviewed": h.reviewed_at.strftime("%Y-%m-%d %H:%M") if h.reviewed_at else None
                })
            st.dataframe(pd.DataFrame(hist_records), use_container_width=True)
            
    db.close()

# ----------------- AI ANALYTICS ASSISTANT PAGE -----------------
elif page == "AI Analytics Assistant":
    st.title("Conversational AI Analytics Assistant")
    st.markdown("Ask natural language questions about your performance diagnostics, trends, or wasted spend, and let the agent run deep dives.")
    st.markdown("---")
    
    if not selected_account:
        st.info("Please select an account scope in the sidebar first.")
    else:
        # Initialize chat history session state
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        # Draw previous messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant" and "trace" in message:
                    with st.expander("Agent Tool Execution Trace"):
                        st.markdown(message["trace"])
                st.markdown(message["content"])
                
        # Handle new user input
        if prompt := st.chat_input("Ask: 'Why did my ROAS drop?' or 'Scan for anomalies'"):
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Generate assistant response
            with st.chat_message("assistant"):
                with st.spinner("Agent running database tools..."):
                    # Call our main agent loop
                    result = run_agent_query(prompt, selected_account.account_id)
                    trace, report = parse_agent_response(result)
                    
                    if trace:
                        with st.expander("Agent Tool Execution Trace"):
                            st.markdown(trace)
                    st.markdown(report)
                    
                    # Save message
                    msg_data = {"role": "assistant", "content": report}
                    if trace:
                        msg_data["trace"] = trace
                    st.session_state.messages.append(msg_data)
