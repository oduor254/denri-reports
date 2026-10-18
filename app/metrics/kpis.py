"""Shared period-filtering and headline-KPI computation, used by every section
module (Executive Summary, Revenue Analysis, the Revenue Bridge, etc.) so the
definition of a metric like "Revenue" or "Customers" is defined exactly once."""
import pandas as pd


def filter_period(df: pd.DataFrame, start, end) -> pd.DataFrame:
    dates = df["Date"].dt.date
    return df[(dates >= start) & (dates <= end)]


def _customer_status(df: pd.DataFrame) -> pd.Series:
    """Repeat flag per unique (valid-phone) customer, based on distinct visit days
    within this period: 2+ different days in the window = Repeat, exactly 1 = New.
    Multiple transactions on the same day count as a single visit. This is
    period-scoped, not the sheet's lifetime Repeat column (which marks whether a
    customer had ever bought before, not whether they visited more than once in
    the selected window)."""
    valid = df[df["Phone Valid"]]
    if valid.empty:
        return pd.Series(dtype=bool)
    return valid.groupby("Phone")["Date"].nunique() >= 2


def compute_kpis(df: pd.DataFrame) -> dict:
    transactions = len(df)
    revenue = float(df["Total"].sum())

    valid_df = df[df["Phone Valid"]]
    customers = int(valid_df["Phone"].nunique())

    status = _customer_status(df)
    repeat = int(status.sum())
    new = int(customers - repeat)

    walkin_df = df[df["Customer Type"] == "walkin"]
    online_df = df[df["Customer Type"] == "online"]
    activation_df = df[df["Customer Type"] == "activation"]
    tagged_df = df[df["Customer Type"].isin(["walkin", "online", "activation", "employee"])]

    return {
        "Transactions": transactions,
        "Revenue": revenue,
        "Customers": customers,
        "New": new,
        "Repeat": repeat,
        "Repeat Rate": (repeat / customers * 100) if customers else 0.0,
        "Avg Rev/Txn": (revenue / transactions) if transactions else 0.0,
        "Avg Spend/Customer": (revenue / customers) if customers else 0.0,
        "Walk-in Avg Spend": float(walkin_df["Total"].mean()) if not walkin_df.empty else 0.0,
        "Online Avg Spend": float(online_df["Total"].mean()) if not online_df.empty else 0.0,
        "Avg Orders": (transactions / customers) if customers else 0.0,
        "Data Quality": (df["Phone Valid"].sum() / transactions * 100) if transactions else 0.0,
        "Activation": (len(activation_df) / transactions * 100) if transactions else 0.0,
        "Customer Type Coverage": (len(tagged_df) / transactions * 100) if transactions else 0.0,
    }


def reconcile_revenue(kpis: dict, revenue_sheet_df: pd.DataFrame, start, end) -> dict:
    """Overrides the Shops-sheet-computed Revenue (and its per-transaction/
    per-customer averages) with the 'Revenue' sheet's hand-reconciled total
    for the same window. The two sources drift apart by small amounts over
    time as entries get corrected at the ledger but not retroactively in the
    raw transaction log, so every 'Revenue' figure in the report - KPI strip,
    Executive Summary, Revenue Analysis, the Revenue Bridge trend - is
    sourced from the reconciled ledger instead of a raw transaction sum, and
    all mean the same number for a given window. Falls back to the original
    Shops-sheet value if the Revenue sheet has no rows for this window (e.g.
    not wired in, or dates outside its coverage)."""
    window = filter_period(revenue_sheet_df, start, end)
    if window.empty:
        return kpis
    retail_total = float(window["Retail Revenue"].sum())
    kpis = dict(kpis)
    kpis["Revenue"] = retail_total
    kpis["Avg Rev/Txn"] = (retail_total / kpis["Transactions"]) if kpis["Transactions"] else 0.0
    kpis["Avg Spend/Customer"] = (retail_total / kpis["Customers"]) if kpis["Customers"] else 0.0
    return kpis
