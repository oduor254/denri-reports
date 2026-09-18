import pandas as pd

from app.metrics import formatting as fmt
from app.metrics.kpis import compute_kpis, filter_period
from app.metrics.periods import sequence_periods

_BRIDGE_COUNTS = {"day": 7, "week": 6, "month": 6}

_KPI_CARD_SPECS = [
    ("Revenue", "Revenue", "money"),
    ("Avg Rev/Txn", "Avg Rev/Txn", "money"),
    ("Avg Spend/Customer", "Avg Spend/Customer", "money"),
    ("Avg Orders/Customer", "Avg Orders", "decimal"),
]

_COMPARISON_SPECS = [
    ("Revenue", "money"),
    ("Avg Rev/Txn", "money"),
    ("Avg Spend/Customer", "money"),
    ("Walk-in Avg Spend", "money"),
    ("Online Avg Spend", "money"),
    ("Avg Orders", "decimal"),
]


def _delta(current: float, previous: float, kind: str):
    if kind == "money":
        return fmt.combined_money_delta(current, previous, places=2)
    return fmt.combined_delta(current, previous, places=2)


def build_kpi_cards(cur_kpis: dict, prev_kpis: dict, compared_to: str) -> list:
    cards = []
    for label, key, kind in _KPI_CARD_SPECS:
        current, previous = cur_kpis[key], prev_kpis[key]
        change, dir_ = _delta(current, previous, kind)
        value = fmt.money(current) if kind == "money" else fmt.decimal(current, 2)
        cards.append({"label": label, "value": value, "sub": f"{change} vs {compared_to}", "tone": dir_})
    return cards


def build_comparison_rows(cur_kpis: dict, prev_kpis: dict) -> list:
    rows = []
    for label, kind in _COMPARISON_SPECS:
        current, previous = cur_kpis[label], prev_kpis[label]
        change, dir_ = _delta(current, previous, kind)
        value_fmt = fmt.money if kind == "money" else (lambda v: fmt.decimal(v, 2))
        rows.append({
            "metric": label,
            "current": value_fmt(current),
            "previous": value_fmt(previous),
            "change": change,
            "dir": dir_,
        })
    return rows


def build_bridge(df: pd.DataFrame, period_type: str, period: dict) -> list:
    count = _BRIDGE_COUNTS.get(period_type, 6)
    windows = sequence_periods(period_type, period["start"], period["end"], count)

    rows = []
    prev_revenue = None
    for w in windows:
        window_df = filter_period(df, w["start"], w["end"])
        kpis = compute_kpis(window_df)

        if prev_revenue is None:
            dir_ = "neutral"
        else:
            dir_ = fmt.direction(fmt.pct_change(kpis["Revenue"], prev_revenue) or 0)

        rows.append({
            "period": w["label"],
            "date_range": w["date_range"],
            "revenue": fmt.money(kpis["Revenue"]),
            "customers": fmt.count(kpis["Customers"]),
            "avg_spend": fmt.money(kpis["Avg Spend/Customer"]),
            "trend": fmt.glyph(dir_),
            "dir": dir_,
            # Raw value for anything that needs to plot this (e.g. the pptx
            # export's revenue-bridge chart) rather than re-parsing "KES 1,234.56".
            "revenue_raw": kpis["Revenue"],
        })
        prev_revenue = kpis["Revenue"]

    return rows


def build_summary(cur_kpis: dict, prev_kpis: dict, bridge: list, period: dict) -> str:
    diff = cur_kpis["Revenue"] - prev_kpis["Revenue"]
    dir_ = fmt.direction(diff)
    trend_word = {"up": "grew", "down": "declined", "neutral": "was flat"}[dir_]
    pc = fmt.pct_change(cur_kpis["Revenue"], prev_kpis["Revenue"])
    pct_str = f" {abs(pc):.1f}%" if pc is not None else ""

    sentences = [
        f"Revenue {trend_word}{pct_str} to {fmt.money(cur_kpis['Revenue'])} vs {period['compared_to']}, "
        f"averaging {fmt.money(cur_kpis['Avg Rev/Txn'])} per transaction and "
        f"{fmt.money(cur_kpis['Avg Spend/Customer'])} per customer."
    ]

    if len(bridge) >= 2:
        first, last = bridge[0], bridge[-1]
        sentences.append(f"Across the trailing {len(bridge)} {period['period_type']}s, revenue moved from {first['revenue']} to {last['revenue']}.")

    return " ".join(sentences)


def build_meeting_note(cur_kpis: dict, prev_kpis: dict, period: dict) -> str:
    pc = fmt.pct_change(cur_kpis["Revenue"], prev_kpis["Revenue"])

    if pc is not None and pc <= -10:
        return f"Revenue is down {abs(pc):.1f}% vs {period['compared_to']} - worth a root-cause review before the next cycle."
    if pc is not None and pc >= 10:
        return f"Revenue is up {pc:.1f}% vs {period['compared_to']} - capture what drove it for the playbook."
    return f"Revenue was broadly stable vs {period['compared_to']} - no escalations needed."


def build_section(df: pd.DataFrame, cur_kpis: dict, prev_kpis: dict, period_type: str, period: dict) -> dict:
    bridge = build_bridge(df, period_type, period)
    return {
        "summary": build_summary(cur_kpis, prev_kpis, bridge, period),
        "kpi_cards": build_kpi_cards(cur_kpis, prev_kpis, period["compared_to"]),
        "comparison": build_comparison_rows(cur_kpis, prev_kpis),
        "bridge": bridge,
        "meeting_note": build_meeting_note(cur_kpis, prev_kpis, period),
    }
