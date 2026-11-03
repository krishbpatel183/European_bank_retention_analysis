"""Shared analytics logic: validation, engagement profiles, KPIs, RSI.
Used by both the Streamlit dashboard (app.py) and the report builder (build_report.py)."""
import numpy as np
import pandas as pd

REQUIRED = ["CustomerId", "Surname", "CreditScore", "Geography", "Gender", "Age", "Tenure",
            "Balance", "NumOfProducts", "HasCrCard", "IsActiveMember", "EstimatedSalary", "Exited"]

PROFILES = ["Active engaged", "Active low-product", "Inactive high-balance", "Inactive disengaged"]


# ------------------------------------------------------------------ 1. Ingestion & validation
def validate(df: pd.DataFrame) -> dict:
    """Return a dict of validation checks (all should be True / 0 for clean data)."""
    missing_cols = [c for c in REQUIRED if c not in df.columns]
    if missing_cols:
        return {"missing_columns": missing_cols}
    return {
        "missing_columns": [],
        "rows": len(df),
        "null_values": int(df[REQUIRED].isna().sum().sum()),
        "duplicate_customer_ids": int(df["CustomerId"].duplicated().sum()),
        "binary_cols_valid": bool(all(df[c].isin([0, 1]).all() for c in ["HasCrCard", "IsActiveMember", "Exited"])),
        "products_range": (int(df.NumOfProducts.min()), int(df.NumOfProducts.max())),
        "negative_balance": int((df.Balance < 0).sum()),
        "zero_balance_share": round(float((df.Balance == 0).mean()), 4),
        "churn_rate": round(float(df.Exited.mean()), 4),
        "geographies": sorted(df.Geography.unique().tolist()),
    }


# ------------------------------------------------------------------ 2. Engagement classification
def add_features(df: pd.DataFrame, high_balance: float = 100_000, ratio_flag: float = 2.0) -> pd.DataFrame:
    """Add engagement profile, balance/salary ratio, mismatch flag, and Relationship Strength Index."""
    d = df.copy()
    active, prod, bal = d.IsActiveMember == 1, d.NumOfProducts, d.Balance

    # Mutually exclusive profiles, evaluated in priority order
    d["Profile"] = np.select(
        [(~active) & (bal >= high_balance),
         (~active),
         active & (prod == 1)],
        ["Inactive high-balance", "Inactive disengaged", "Active low-product"],
        default="Active engaged")

    d["BalanceSalaryRatio"] = d.Balance / d.EstimatedSalary
    d["SalaryBalanceMismatch"] = d.BalanceSalaryRatio >= ratio_flag
    d["HighBalance"] = bal >= high_balance
    d["AtRiskPremium"] = (~active) & d.HighBalance

    # ---- Relationship Strength Index (0-100) ----
    # Product score is data-driven: observed retention rate for each product count, so the
    # index does not wrongly assume "more products = better" (3-4 products churn heavily).
    ret_by_prod = 1 - d.groupby("NumOfProducts").Exited.mean()
    prod_score = d.NumOfProducts.map(ret_by_prod)
    tenure_score = d.Tenure / max(d.Tenure.max(), 1)
    # Weights: activity 30, product mix 60, tenure 10. Credit card gets 0 weight because the
    # Credit Card Stickiness KPI shows card ownership has almost no retention effect.
    d["RSI"] = 100 * (0.30 * d.IsActiveMember + 0.60 * prod_score + 0.10 * tenure_score)
    d["RSI_Tier"] = pd.cut(d.RSI, [-0.1, 40, 60, 80, 100.1], labels=["Weak (<40)", "Moderate (40-60)", "Strong (60-80)", "Very strong (80+)"])
    d["Sticky"] = (d.IsActiveMember == 1) & (d.NumOfProducts == 2)
    return d


# ------------------------------------------------------------------ helpers
def churn_table(d: pd.DataFrame, by) -> pd.DataFrame:
    t = d.groupby(by, observed=True).agg(Customers=("Exited", "size"), Churned=("Exited", "sum"),
                                         ChurnRate=("Exited", "mean")).reset_index()
    t["ChurnRate"] = (t.ChurnRate * 100).round(2)
    return t


# ------------------------------------------------------------------ KPIs
def kpis(d: pd.DataFrame) -> dict:
    act, ina = d[d.IsActiveMember == 1], d[d.IsActiveMember == 0]
    ret_act, ret_ina = 1 - act.Exited.mean(), 1 - ina.Exited.mean()
    overall_ret = 1 - d.Exited.mean()
    ret_by_prod = (1 - d.groupby("NumOfProducts").Exited.mean())
    hb = d[(d.IsActiveMember == 0) & d.HighBalance]
    card, nocard = d[d.HasCrCard == 1], d[d.HasCrCard == 0]
    return {
        # churn(inactive) / churn(active): how many times more likely an inactive member is to leave
        "Engagement Retention Ratio": round(ina.Exited.mean() / act.Exited.mean(), 2) if act.Exited.mean() else np.nan,
        "Churn - Active (%)": round(act.Exited.mean() * 100, 2),
        "Churn - Inactive (%)": round(ina.Exited.mean() * 100, 2),
        # retention of best product count relative to the overall retention
        "Product Depth Index": {int(k): round(v / overall_ret, 3) for k, v in ret_by_prod.items()},
        "High-Balance Disengagement Rate (%)": round(hb.Exited.mean() * 100, 2) if len(hb) else np.nan,
        "At-risk premium customers": int(len(hb)),
        # retention gap (percentage points): card holders minus non-holders
        "Credit Card Stickiness Score (pp)": round((card.Exited.mean() - nocard.Exited.mean()) * -100, 2),
        "Average RSI": round(d.RSI.mean(), 1),
    }
