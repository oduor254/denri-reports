"""Corporate channel reporting - additive to the rest of the report, not a
re-tag of existing data: Corporate sales (bulk/B2B, handled by named sales
reps per the 'Corporate' sheet) are recorded in a separate daily ledger (the
'Revenue' sheet's CORPORATE column) and aren't present in the Shops sheet's
per-transaction rows at all. The existing 'Revenue' KPI/metric is left
untouched everywhere it already appears - this adds Corporate Revenue as its
own tracked line, plus an explicit 'Overall Revenue' (retail + corporate)
figure, per user request, rather than silently folding corporate sales into
the already-verified headline Revenue number.
"""
import pandas as pd

from app.metrics import formatting as fmt
from app.metrics.kpis import filter_period


def _corporate_revenue(revenue_sheet_df: pd.DataFrame, start, end) -> float:
    window = filter_period(revenue_sheet_df, start, end)
    return float(window["Corporate Revenue"].sum()) if not window.empty else 0.0


def build_comparison_rows(revenue_sheet_df: pd.DataFrame, cur_retail_revenue: float, prev_retail_revenue: float, period: dict) -> list:
    cur_corp = _corporate_revenue(revenue_sheet_df, period["start"], period["end"])
    prev_corp = _corporate_revenue(revenue_sheet_df, period["prev_start"], period["prev_end"])
    cur_overall = cur_retail_revenue + cur_corp
    prev_overall = prev_retail_revenue + prev_corp

    rows = []
    for label, current, previous in (
        ("Corporate Revenue", cur_corp, prev_corp),
        ("Overall Revenue", cur_overall, prev_overall),
    ):
        change, dir_ = fmt.combined_money_delta(current, previous)
        rows.append({
            "metric": label, "current": fmt.money(current), "previous": fmt.money(previous),
            "change": change, "dir": dir_, "current_raw": current, "previous_raw": previous,
        })
    return rows


def build_overall_kpi_card(comparison: list, compared_to: str) -> dict:
    overall = next(r for r in comparison if r["metric"] == "Overall Revenue")
    change, dir_ = fmt.combined_money_delta(overall["current_raw"], overall["previous_raw"])
    return {
        "label": "Overall Revenue (incl. Corporate)",
        "value": fmt.money(overall["current_raw"]),
        "sub": f"{change} vs {compared_to}",
        "tone": dir_,
    }


def build_client_rows(corporate_df: pd.DataFrame) -> list:
    if corporate_df.empty:
        return []

    df = corporate_df.sort_values("Revenue", ascending=False)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "customer": r["Customer"],
            "orders": fmt.count(r["Orders"]),
            "bags": fmt.count(r["Bags"]),
            "revenue": fmt.money(r["Revenue"]),
            "first_order": r["First Order"],
            "last_order": r["Last Order"],
            "served_by": r["Served By"],
            "orders_raw": int(r["Orders"]),
            "bags_raw": int(r["Bags"]),
            "revenue_raw": float(r["Revenue"]),
        })

    total_orders, total_bags, total_revenue = int(df["Orders"].sum()), int(df["Bags"].sum()), float(df["Revenue"].sum())
    rows.append({
        "customer": "TOTAL",
        "orders": fmt.count(total_orders),
        "bags": fmt.count(total_bags),
        "revenue": fmt.money(total_revenue),
        "first_order": "", "last_order": "", "served_by": "",
        "orders_raw": total_orders, "bags_raw": total_bags, "revenue_raw": total_revenue,
    })
    return rows


def build_summary(comparison: list, client_rows: list, period: dict) -> str:
    corp = next(r for r in comparison if r["metric"] == "Corporate Revenue")
    overall = next(r for r in comparison if r["metric"] == "Overall Revenue")
    share = (corp["current_raw"] / overall["current_raw"] * 100) if overall["current_raw"] else 0.0

    dir_word = {"up": "up", "down": "down", "neutral": "flat"}[corp["dir"]]
    pc = fmt.pct_change(corp["current_raw"], corp["previous_raw"])
    pct_str = f" {abs(pc):.1f}%" if pc is not None else ""

    sentences = [
        f"Corporate revenue was {corp['current']} this period ({dir_word}{pct_str} vs {period['compared_to']}), "
        f"{share:.1f}% of {overall['current']} in overall (retail + corporate) revenue."
    ]

    client_count = max(len(client_rows) - 1, 0)  # exclude TOTAL row
    if client_count:
        top_client = client_rows[0]
        sentences.append(
            f"{client_count} corporate client(s) on record all-time; the largest is "
            f"{top_client['customer']} at {top_client['revenue']} lifetime."
        )
    return " ".join(sentences)


def build_meeting_note(comparison: list, period: dict) -> str:
    corp = next(r for r in comparison if r["metric"] == "Corporate Revenue")
    pc = fmt.pct_change(corp["current_raw"], corp["previous_raw"])

    if pc is not None and pc <= -15:
        return f"Corporate revenue is down {abs(pc):.1f}% vs {period['compared_to']} - worth checking in with key accounts."
    if pc is not None and pc >= 15:
        return f"Corporate revenue is up {pc:.1f}% vs {period['compared_to']} - good momentum with corporate accounts."
    return f"Corporate revenue was broadly stable vs {period['compared_to']}."


def build_section(revenue_sheet_df: pd.DataFrame, corporate_df: pd.DataFrame, cur_retail_revenue: float, prev_retail_revenue: float, period: dict) -> dict:
    comparison = build_comparison_rows(revenue_sheet_df, cur_retail_revenue, prev_retail_revenue, period)
    client_rows = build_client_rows(corporate_df)
    return {
        "summary": build_summary(comparison, client_rows, period),
        "comparison": comparison,
        "clients": client_rows,
        "kpi_card": build_overall_kpi_card(comparison, period["compared_to"]),
        "meeting_note": build_meeting_note(comparison, period),
    }
