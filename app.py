"""
app.py
Streamlit UI for the Travel Reimbursement Approval Agent.

Run with: streamlit run app.py
Requires OPENAI_API_KEY to be set in the environment (or a .env file).
"""
import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import run_agent
from tools import load_policy_text

st.set_page_config(page_title="Travel Reimbursement Approval Agent", layout="wide")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DECISION_COLORS = {
    "Approve": "#1e7e34",
    "Partially Approve": "#b8860b",
    "Reject": "#b02a37",
    "Manual Review": "#5a5fcf",
}


@st.cache_data
def load_sample_claims():
    with open(os.path.join(DATA_DIR, "sample_claims.json")) as f:
        return json.load(f)


def render_decision_card(decision: dict):
    color = DECISION_COLORS.get(decision.get("decision"), "#444")
    st.markdown(
        f"""
        <div style="border-left: 6px solid {color}; padding: 12px 18px; background: rgba(127,127,127,0.08); border-radius: 6px;">
            <h3 style="margin:0; color:{color};">{decision.get('decision', 'N/A')}</h3>
            <p style="margin:4px 0 0 0;">{decision.get('explanation', '')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Claimed", f"${decision.get('total_claimed_amount', 0):.2f}")
    c2.metric("Approved", f"${decision.get('approved_amount', 0):.2f}")
    c3.metric("Deducted/Rejected", f"${decision.get('deducted_or_rejected_amount', 0):.2f}")
    c4.metric("Confidence", f"{decision.get('confidence', 0):.0%}")

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Reason Codes**")
        codes = decision.get("reason_codes", [])
        st.write(", ".join(codes) if codes else "-")
        st.markdown("**Missing Documents**")
        missing = decision.get("missing_documents", [])
        st.write(", ".join(missing) if missing else "None")
    with colB:
        st.markdown("**Policy References**")
        refs = decision.get("policy_references", [])
        if refs:
            for r in refs:
                st.text(f"• {r}")
        else:
            st.text("-")
        if decision.get("_original_llm_decision") and decision["_original_llm_decision"] != decision["decision"]:
            st.caption(f"⚠️ Guardrail overrode LLM's initial decision of '{decision['_original_llm_decision']}'.")


def render_audit_trail(audit_trail: list):
    st.markdown("### 🔍 Audit Trail - Tools Called & Intermediate Checks")
    for entry in audit_trail:
        label = f"Step {entry['step']}: `{entry['tool_called']}`"
        with st.expander(label, expanded=False):
            st.markdown("**Arguments:**")
            st.json(entry["arguments"])
            st.markdown("**Result:**")
            st.json(entry["result"])

# ✅ Define modal dialog
@st.dialog("📄 Policy Document")
def show_policy_dialog():
    try:
        policy_md = load_policy_text()
        st.markdown(policy_md, width='stretch')
    except FileNotFoundError:
        st.error("policy.md file not found.")

    # Close button (optional, dialog already has X)
    if st.button("Close"):
        st.rerun()

def main():
    st.title("🧾 Travel Reimbursement Approval Agent")
    st.caption("GenAI agent (Groq tool calling) evaluating claims against mock Sahil Corp travel policy.")

    if not os.environ.get("GROQ_API_KEY"):
        st.warning("GROQ_API_KEY is not set. Add it to your environment or a .env file before running an evaluation.")

    samples = load_sample_claims()
    sample_lookup = {f"{c['claim_id']} - {c['employee_name']} ({c['destination_city']})": c for c in samples}

    with st.sidebar:
        st.header("Claim Input")
        mode = st.radio("Source", ["Pick a sample claim", "Paste custom JSON"])

        claim = None
        if mode == "Pick a sample claim":
            choice = st.selectbox("Sample claim", list(sample_lookup.keys()))
            claim = sample_lookup[choice]
            st.json(claim, expanded=False)
        else:
            raw = st.text_area("Claim JSON", height=300, placeholder='{\n  "claim_id": "...",\n  ...\n}')
            if raw.strip():
                try:
                    claim = json.loads(raw)
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        run_clicked = st.button("▶ Run Evaluation", type="primary", width='stretch')

    if "history" not in st.session_state:
        st.session_state.history = []

    if run_clicked and claim:
        with st.spinner("Agent is retrieving policy context and running checks..."):
            result = run_agent(claim)
        st.session_state.history.insert(0, {"claim": claim, "result": result})

    if not st.session_state.history:
        st.info("Select or paste a claim, then click **Run Evaluation** to see the agent's decision.")
        return

    latest = st.session_state.history[0]
    st.subheader(f"Result for {latest['claim'].get('claim_id', 'claim')}")
    render_decision_card(latest["result"]["final_decision"])

    tab1, tab2, tab3 = st.tabs(["Audit Trail", "Original Claim", "Raw JSON Output"])
    with tab1:
        render_audit_trail(latest["result"]["audit_trail"])
    with tab2:
        st.json(latest["claim"])
    with tab3:
        st.json(latest["result"]["final_decision"])

    if len(st.session_state.history) > 1:
        st.markdown("---")
        st.markdown("### 📜 Session History & Insights")

        rows = []
        for h in st.session_state.history:
            d = h["result"]["final_decision"]
            rows.append({
                "Claim ID": d.get("claim_id"),
                "Decision": d.get("decision"),
                "Claimed ($)": d.get("total_claimed_amount"),
                "Approved ($)": d.get("approved_amount"),
                "Deducted ($)": d.get("deducted_or_rejected_amount"),
                "Confidence": f"{d.get('confidence', 0):.0%}",
                "Reason Codes": ", ".join(d.get("reason_codes", [])),
            })

        # ── Summary metric tiles ──────────────────────────────────────────
        total_claimed  = sum(h["result"]["final_decision"].get("total_claimed_amount", 0) for h in st.session_state.history)
        total_approved = sum(h["result"]["final_decision"].get("approved_amount", 0) for h in st.session_state.history)
        total_deducted = sum(h["result"]["final_decision"].get("deducted_or_rejected_amount", 0) for h in st.session_state.history)
        avg_confidence = sum(h["result"]["final_decision"].get("confidence", 0) for h in st.session_state.history) / len(st.session_state.history)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Claimed",   f"${total_claimed:,.2f}")
        m2.metric("Total Approved",  f"${total_approved:,.2f}")
        m3.metric("Total Deducted",  f"${total_deducted:,.2f}")
        m4.metric("Avg Confidence",  f"{avg_confidence:.0%}")

        # ── Charts side by side ──────────────────────────────────────────
        import plotly.express as px
        import plotly.graph_objects as go
        import pandas as pd

        df = pd.DataFrame(rows)
        decisions = [r["Decision"] for r in rows]
        counts = {d: decisions.count(d) for d in set(decisions)}

        col_pie, col_bar = st.columns(2)

        with col_pie:
            st.markdown("**Decision Breakdown**")
            color_map = {
                "Approve":          "#1e7e34",
                "Partially Approve":"#b8860b",
                "Reject":           "#b02a37",
                "Manual Review":    "#5a5fcf",
            }
            fig_pie = px.pie(
                names=list(counts.keys()),
                values=list(counts.values()),
                color=list(counts.keys()),
                color_discrete_map=color_map,
                hole=0.4,           # donut style - easier to read counts
            )
            fig_pie.update_traces(textposition="outside", textinfo="percent+label")
            fig_pie.update_layout(margin=dict(t=10, b=10), showlegend=False)
            st.plotly_chart(fig_pie, width='stretch')

        with col_bar:
            st.markdown("**Claimed vs Approved per Claim**")
            fig_bar = go.Figure(data=[
                go.Bar(name="Claimed",  x=df["Claim ID"], y=df["Claimed ($)"],  marker_color="#4a90d9"),
                go.Bar(name="Approved", x=df["Claim ID"], y=df["Approved ($)"], marker_color="#1e7e34"),
            ])
            fig_bar.update_layout(
                barmode="group",
                margin=dict(t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                xaxis_title=None,
                yaxis_title="Amount ($)",
            )
            st.plotly_chart(fig_bar, width='stretch')

        # ── Detailed history table ────────────────────────────────────────
        st.markdown("**All Evaluated Claims**")
        st.dataframe(df, width='stretch', hide_index=True)


if __name__ == "__main__":
    main()
