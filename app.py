"""Customer Engagement & Product Utilization Analytics for Retention Strategy
Run:  streamlit run app.py
Place European_Bank.xlsx next to this file, or upload it in the sidebar."""
import os
import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import PROFILES, add_features, churn_table, kpis, validate

st.set_page_config(page_title="Retention Analytics", page_icon="🏦", layout="wide")


@st.cache_data
def load(src):
    name = getattr(src, "name", str(src)).lower()
    return pd.read_excel(src) if name.endswith((".xlsx", ".xls")) else pd.read_csv(src)


# ------------------------------------------------------------------ Sidebar: data + filters
st.sidebar.title("🏦 Retention Analytics")
up = st.sidebar.file_uploader("Upload dataset (xlsx or csv)", type=["xlsx", "xls", "csv"])
if up is not None:
    raw = load(up)
else:
    default = next((p for p in ["European_Bank.xlsx", "Churn_Modelling.csv"] if os.path.exists(p)), None)
    if default is None:
        st.info("Upload the dataset in the sidebar (or put European_Bank.xlsx next to app.py).")
        st.stop()
    raw = load(default)

checks = validate(raw)
if checks["missing_columns"]:
    st.error(f"Missing columns: {checks['missing_columns']}")
    st.stop()

st.sidebar.header("Thresholds")
hb = st.sidebar.slider("High-balance threshold", 0, 250_000, 100_000, 5_000)
ratio = st.sidebar.slider("Balance ÷ salary mismatch ratio", 0.5, 5.0, 2.0, 0.5)
df = add_features(raw, high_balance=hb, ratio_flag=ratio)

st.sidebar.header("Filters")
eng = st.sidebar.multiselect("Engagement profile", PROFILES, default=PROFILES)
act = st.sidebar.radio("Activity status", ["All", "Active", "Inactive"], horizontal=True)
pmin, pmax = st.sidebar.slider("Number of products", 1, 4, (1, 4))
bmin, bmax = st.sidebar.slider("Balance range", 0, int(df.Balance.max()) + 1, (0, int(df.Balance.max()) + 1), 5_000)
smin, smax = st.sidebar.slider("Salary range", 0, int(df.EstimatedSalary.max()) + 1, (0, int(df.EstimatedSalary.max()) + 1), 5_000)
geo = st.sidebar.multiselect("Geography", sorted(df.Geography.unique()), default=sorted(df.Geography.unique()))
card = st.sidebar.radio("Credit card", ["All", "Has card", "No card"], horizontal=True)

f = df[df.Profile.isin(eng) & df.NumOfProducts.between(pmin, pmax) & df.Balance.between(bmin, bmax)
       & df.EstimatedSalary.between(smin, smax) & df.Geography.isin(geo)]
if act != "All":
    f = f[f.IsActiveMember == (1 if act == "Active" else 0)]
if card != "All":
    f = f[f.HasCrCard == (1 if card == "Has card" else 0)]

st.title("Customer Engagement & Product Utilization Analytics")
st.caption("Retention strategy through behaviour and relationship strength, not demographics.")
if f.empty:
    st.warning("No customers match the current filters.")
    st.stop()

k = kpis(f) if f.IsActiveMember.nunique() == 2 and f.HasCrCard.nunique() == 2 else None
c = st.columns(5)
c[0].metric("Customers", f"{len(f):,}")
c[1].metric("Churn rate", f"{f.Exited.mean()*100:.1f}%")
if k:
    c[2].metric("Engagement Retention Ratio", f"{k['Engagement Retention Ratio']}×", help="Churn(inactive) ÷ churn(active)")
    c[3].metric("High-Balance Disengagement", f"{k['High-Balance Disengagement Rate (%)']}%", help="Churn among inactive customers above the balance threshold")
    c[4].metric("Credit Card Stickiness", f"{k['Credit Card Stickiness Score (pp)']:+} pp", help="Retention gap, card holders minus non-holders")
else:
    c[2].metric("Avg RSI", f"{f.RSI.mean():.1f}")

tabs = st.tabs(["Engagement vs churn", "Product utilization", "High-value disengaged", "Retention strength", "Data quality"])

# ------------------------------------------------------------------ 1. Engagement overview
with tabs[0]:
    a, b = st.columns(2)
    t = churn_table(f, "Profile")
    a.plotly_chart(px.bar(t, x="Profile", y="ChurnRate", text="ChurnRate", color="Profile",
                          title="Churn rate by engagement profile (%)"), width='stretch')
    t2 = churn_table(f.assign(Status=f.IsActiveMember.map({1: "Active", 0: "Inactive"})), "Status")
    b.plotly_chart(px.bar(t2, x="Status", y="ChurnRate", text="ChurnRate", color="Status",
                          title="Active vs inactive churn (%)"), width='stretch')
    st.dataframe(t, hide_index=True, width='stretch')

# ------------------------------------------------------------------ 2. Product utilization
with tabs[1]:
    a, b = st.columns(2)
    t = churn_table(f, "NumOfProducts")
    a.plotly_chart(px.bar(t, x="NumOfProducts", y="ChurnRate", text="ChurnRate", title="Churn rate by number of products (%)"),
                   width='stretch')
    t3 = churn_table(f.assign(Status=f.IsActiveMember.map({1: "Active", 0: "Inactive"})), ["NumOfProducts", "Status"])
    b.plotly_chart(px.bar(t3, x="NumOfProducts", y="ChurnRate", color="Status", barmode="group", text="ChurnRate",
                          title="Product count × activity (%)"), width='stretch')
    sm = f.assign(Depth=f.NumOfProducts.map(lambda n: "Single product" if n == 1 else "Multi-product"))
    st.subheader("Single vs multi-product retention")
    st.dataframe(churn_table(sm, "Depth"), hide_index=True, width='stretch')
    st.caption("Sweet spot: 2 products. Customers with 3–4 products churn far more, which suggests over-selling or product dissatisfaction.")
    cc = churn_table(f.assign(Card=f.HasCrCard.map({1: "Has credit card", 0: "No credit card"})), "Card")
    st.dataframe(cc, hide_index=True, width='stretch')

# ------------------------------------------------------------------ 3. High-value disengaged detector
with tabs[2]:
    risk = f[f.AtRiskPremium]
    m = st.columns(3)
    m[0].metric("At-risk premium customers", f"{len(risk):,}")
    m[1].metric("Already churned", f"{int(risk.Exited.sum()):,}")
    m[2].metric("Balance at stake (churned)", f"{risk[risk.Exited == 1].Balance.sum():,.0f}")
    bins = f.assign(BalanceBand=pd.cut(f.Balance, [-1, 0, 50_000, 100_000, 150_000, 300_000],
                                       labels=["0", "1-50k", "50-100k", "100-150k", "150k+"]),
                    Status=f.IsActiveMember.map({1: "Active", 0: "Inactive"}))
    h = churn_table(bins, ["BalanceBand", "Status"])
    st.plotly_chart(px.bar(h, x="BalanceBand", y="ChurnRate", color="Status", barmode="group", text="ChurnRate",
                           title="Balance × activity cross-analysis: churn rate (%)"), width='stretch')
    mm = f[f.SalaryBalanceMismatch]
    st.write(f"**Salary–balance mismatch** (balance ≥ {ratio}× salary): {len(mm):,} customers, churn {mm.Exited.mean()*100:.1f}% "
             f"vs {f[~f.SalaryBalanceMismatch].Exited.mean()*100:.1f}% for the rest.")
    st.subheader("Priority outreach list (still with the bank)")
    watch = risk[risk.Exited == 0].sort_values(["Balance", "RSI"], ascending=[False, True])
    cols = ["CustomerId", "Surname", "Geography", "Age", "Balance", "EstimatedSalary", "NumOfProducts", "RSI", "Tenure"]
    st.dataframe(watch[cols].round(1), hide_index=True, width='stretch')
    st.download_button("Download list (CSV)", watch[cols].to_csv(index=False), "at_risk_premium.csv", "text/csv")

# ------------------------------------------------------------------ 4. Retention strength
with tabs[3]:
    a, b = st.columns(2)
    tt = churn_table(f, "RSI_Tier")
    a.plotly_chart(px.bar(tt, x="RSI_Tier", y="ChurnRate", text="ChurnRate", title="Churn by Relationship Strength tier (%)"),
                   width='stretch')
    b.plotly_chart(px.histogram(f, x="RSI", color=f.Exited.map({0: "Stayed", 1: "Churned"}), nbins=40, barmode="overlay",
                                title="RSI distribution"), width='stretch')
    s = f[f.Sticky]
    st.write(f"**Sticky customers** (active + exactly 2 products): {len(s):,} ({len(s)/len(f)*100:.1f}% of base), "
             f"churn {s.Exited.mean()*100:.1f}% vs {f[~f.Sticky].Exited.mean()*100:.1f}% for everyone else.")
    th = st.slider("Engagement threshold: minimum RSI", 0, 100, 60)
    above, below = f[f.RSI >= th], f[f.RSI < th]
    x = st.columns(2)
    x[0].metric(f"Churn at RSI ≥ {th}", f"{above.Exited.mean()*100:.1f}%" if len(above) else "n/a", f"{len(above):,} customers")
    x[1].metric(f"Churn at RSI < {th}", f"{below.Exited.mean()*100:.1f}%" if len(below) else "n/a", f"{len(below):,} customers")
    st.caption("RSI = 30% activity + 60% product-mix retention score + 10% tenure (0–100). Credit card gets no weight because it shows almost no retention effect.")

# ------------------------------------------------------------------ 5. Data quality
with tabs[4]:
    st.json({k_: (v if not isinstance(v, tuple) else list(v)) for k_, v in checks.items()})
    st.dataframe(raw.head(50), width='stretch')
