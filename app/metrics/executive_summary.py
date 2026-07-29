from datetime import datetime

import pandas as pd

from app.metrics import (
    customer_metrics, data_quality, feedback, formatting as fmt, gender_performance, priorities,
    revenue, store_performance, traffic,
)
from app.metrics.kpis import compute_kpis, filter_period
from app.metrics.periods import resolve_period

# metric key -> (display label, value kind)
# kind drives both formatting and whether the delta is expressed as a % change
# (money/count/decimal) or a percentage-point change (pct).
METRIC_SPECS = [
    ("Revenue", "money"),
    ("Customers", "count"),
    ("New", "count"),
    ("Repeat", "count"),
    ("Repeat Rate", "pct"),
    ("Avg Rev/Txn", "money"),
    ("Avg Spend/Customer", "money"),
    ("Walk-in Avg Spend", "money"),
    ("Online Avg Spend", "money"),
    ("Avg Orders", "decimal"),
    ("Data Quality", "pct"),
    ("Activation", "pct"),
]

_FORMATTERS = {
    "money": fmt.money,
    "count": fmt.count,
    "pct": fmt.pct,
    "decimal": fmt.decimal,
}

# Minimum movement before a metric counts as a notable mover for flags/narrative.
# money/count/decimal are % change vs prior period; pct metrics are percentage points.
_MOVER_THRESHOLDS = {"money": 5.0, "count": 5.0, "decimal": 8.0, "pct": 3.0}


def _metric_delta(kind: str, current: float, previous: float):
    if kind == "pct" or kind == "decimal":
        delta = current - previous
    else:
        pc = fmt.pct_change(current, previous)
        delta = pc if pc is not None else (current - (previous or 0))

    dir_ = fmt.direction(delta)

    if kind == "pct":
        change_str = f"{fmt.glyph(dir_)} {fmt.pp(delta)}"
    elif kind == "decimal":
        sign = "+" if delta >= 0 else ""
        change_str = f"{fmt.glyph(dir_)} {sign}{delta:.1f}"
    else:
        pc = fmt.pct_change(current, previous)
        if pc is None:
            change_str = f"{fmt.glyph(dir_)} n/a"
        else:
            sign = "+" if pc >= 0 else ""
            change_str = f"{fmt.glyph(dir_)} {sign}{pc:.1f}%"

    return change_str, dir_


def evaluate_metrics(cur_kpis: dict, prev_kpis: dict) -> list:
    """Every METRIC_SPECS row, fully evaluated: formatted values, the change
    string/direction, and a `ratio` (how many multiples of its own "notable
    movement" threshold this metric moved). `ratio >= 1` means the move is
    significant enough to surface as an automatic insight. This single pass
    feeds the comparison table, the flags, and the narrative, so "what counts
    as notable" is defined once and applied uniformly instead of per-metric
    hardcoded checks."""
    evaluated = []
    for label, kind in METRIC_SPECS:
        current = cur_kpis[label]
        previous = prev_kpis[label]
        change_str, dir_ = _metric_delta(kind, current, previous)

        if kind == "pct":
            severity = abs(current - previous)
            magnitude = f"{severity:.1f} pp"
        else:
            pc = fmt.pct_change(current, previous)
            severity = abs(pc) if pc is not None else 0.0
            magnitude = f"{severity:.1f}%"

        threshold = _MOVER_THRESHOLDS[kind]
        evaluated.append({
            "metric": label,
            "kind": kind,
            "current_raw": current,
            "previous_raw": previous,
            "current": _FORMATTERS[kind](current),
            "previous": _FORMATTERS[kind](previous),
            "change": change_str,
            "dir": dir_,
            "magnitude": magnitude,  # unsigned, e.g. "13.0%" / "3.2 pp" - pair with dir/verb wording
            "ratio": (severity / threshold) if threshold else 0.0,
        })
    return evaluated


def build_comparison_rows(evaluated: list) -> list:
    return [
        {"metric": e["metric"], "current": e["current"], "previous": e["previous"], "change": e["change"], "dir": e["dir"]}
        for e in evaluated
    ]


def build_kpi_strip(cur_kpis: dict, prev_kpis: dict, compared_to: str) -> list:
    cards = [
        ("Revenue", "money", cur_kpis["Revenue"], prev_kpis["Revenue"]),
        ("Total Customers", "count", cur_kpis["Customers"], prev_kpis["Customers"]),
        ("Avg Spend/Customer", "money", cur_kpis["Avg Spend/Customer"], prev_kpis["Avg Spend/Customer"]),
        ("Repeat Rate", "pct", cur_kpis["Repeat Rate"], prev_kpis["Repeat Rate"]),
        ("Data Quality", "pct", cur_kpis["Data Quality"], prev_kpis["Data Quality"]),
    ]
    strip = []
    for label, kind, current, previous in cards:
        change_str, dir_ = _metric_delta(kind, current, previous)
        strip.append({
            "label": label,
            "value": _FORMATTERS[kind](current),
            "sub": f"{change_str} vs {compared_to}",
            "tone": dir_,
        })
    return strip


def build_context_note(period: dict, cur_kpis: dict) -> str:
    note = (
        f"This report covers {period['days']} trading day(s): {period['date_range']}, "
        f"compared to {period['compared_to']}."
    )
    if cur_kpis["Customer Type Coverage"] < 80:
        note += (
            " Note: Customer Type (walk-in/online/activation) tagging was inconsistently "
            "recorded for part of this period, so channel-mix figures below may be incomplete."
        )
    return note


_MAX_MOVER_FLAGS = 5


def build_flags(evaluated: list, cur_kpis: dict, compared_to: str) -> list:
    flags = []

    movers = sorted(
        (e for e in evaluated if e["dir"] != "neutral" and e["ratio"] >= 1),
        key=lambda e: e["ratio"],
        reverse=True,
    )
    for e in movers[:_MAX_MOVER_FLAGS]:
        verb = "up" if e["dir"] == "up" else "down"
        kind = "positive" if e["dir"] == "up" else "risk"
        flags.append({"text": f"{e['metric']} is {verb} {e['magnitude']} vs {compared_to}.", "kind": kind})

    if cur_kpis["Data Quality"] < 90:
        flags.append({
            "text": f"Data quality (valid phone capture) is at {cur_kpis['Data Quality']:.1f}%, below the 90% target.",
            "kind": "watch",
        })

    if cur_kpis["Customer Type Coverage"] < 80:
        flags.append({
            "text": f"Only {cur_kpis['Customer Type Coverage']:.1f}% of transactions this period have a Customer Type tag.",
            "kind": "watch",
        })

    if not flags:
        flags.append({"text": "No material deviations flagged for this period.", "kind": "key"})

    return flags


def build_narrative(period: dict, cur_kpis: dict, prev_kpis: dict, evaluated: list) -> str:
    by_metric = {e["metric"]: e for e in evaluated}
    rev = by_metric["Revenue"]
    cust = by_metric["Customers"]
    trend_word = {"up": "up", "down": "down", "neutral": "flat"}[rev["dir"]]
    cust_word = {"up": "up", "down": "down", "neutral": "flat"}[cust["dir"]]

    sentences = [
        f"Over {period['date_range']} ({period['days']} trading day(s)), Denri Africa generated "
        f"{fmt.money(cur_kpis['Revenue'])} in revenue from {fmt.count(cur_kpis['Customers'])} customers "
        f"({fmt.count(cur_kpis['New'])} new, {fmt.count(cur_kpis['Repeat'])} repeat). "
        f"Revenue was {trend_word} {rev['magnitude']} and customer count moved {cust_word} "
        f"{cust['magnitude']} compared to {period['compared_to']}."
    ]

    # Automatically surface the single strongest improvement / decline elsewhere
    # in the KPI set, so the narrative isn't limited to hardcoded metrics.
    others = [e for e in evaluated if e["metric"] not in ("Revenue", "Customers")]
    best = max((e for e in others if e["dir"] == "up"), key=lambda e: e["ratio"], default=None)
    worst = max((e for e in others if e["dir"] == "down"), key=lambda e: e["ratio"], default=None)

    if best and best["ratio"] >= 1:
        sentences.append(f"The strongest improvement was {best['metric']} (up {best['magnitude']}).")
    if worst and worst["ratio"] >= 1:
        sentences.append(f"The steepest decline was {worst['metric']} (down {worst['magnitude']}).")

    sentences.append(
        f"Repeat rate stood at {fmt.pct(cur_kpis['Repeat Rate'])}, and phone-capture data quality "
        f"was {fmt.pct(cur_kpis['Data Quality'])}."
    )
    return " ".join(sentences)


def build_meeting_note(evaluated: list, cur_kpis: dict, period: dict) -> str:
    """A short, auto-generated review note: a headline verdict plus the one thing
    most worth investigating and the one thing most worth repeating, derived
    entirely from this period's numbers (no fabricated commentary)."""
    by_metric = {e["metric"]: e for e in evaluated}
    rev = by_metric["Revenue"]

    if rev["dir"] == "down":
        verdict = f"Revenue softened {rev['magnitude']} vs {period['compared_to']}."
    elif rev["dir"] == "up":
        verdict = f"Revenue grew {rev['magnitude']} vs {period['compared_to']}."
    else:
        verdict = f"Revenue was flat vs {period['compared_to']}."

    sentences = [verdict]

    others = [e for e in evaluated if e["metric"] != "Revenue"]
    worst = max((e for e in others if e["dir"] == "down"), key=lambda e: e["ratio"], default=None)
    best = max((e for e in others if e["dir"] == "up"), key=lambda e: e["ratio"], default=None)

    if worst and worst["ratio"] >= 1:
        sentences.append(
            f"Biggest concern to review: {worst['metric']} down {worst['magnitude']} — confirm whether "
            "this is seasonal, channel-specific, or a data-capture gap before the next cycle."
        )
    if best and best["ratio"] >= 1:
        sentences.append(
            f"Biggest win to reinforce: {best['metric']} up {best['magnitude']} — worth identifying "
            "what drove it so it can be repeated."
        )
    if cur_kpis["Data Quality"] < 90 or cur_kpis["Customer Type Coverage"] < 80:
        sentences.append("Also flag phone/channel data-capture gaps with store teams.")

    if len(sentences) == 1:
        sentences.append(f"No material deviations this period vs {period['compared_to']} — steady as she goes.")

    return " ".join(sentences)


def build_report(
    df: pd.DataFrame, period_type: str, ref_date=None,
    footfall_df: pd.DataFrame = None, footfall_gaps: list = None,
    feedback_daily_df: pd.DataFrame = None, feedback_by_shop_df: pd.DataFrame = None,
    feedback_links_df: pd.DataFrame = None,
) -> dict:
    if footfall_df is None:
        footfall_df = pd.DataFrame(columns=["Shop", "Date", "Walkins Purchased", "Walkins Not Purchased", "Total"])
    if feedback_daily_df is None:
        feedback_daily_df = pd.DataFrame(columns=["Date", "Responses", "Professionalism", "Overall"])
    if feedback_by_shop_df is None:
        feedback_by_shop_df = pd.DataFrame(columns=["Date", "Shop", "Responses"])
    if feedback_links_df is None:
        feedback_links_df = pd.DataFrame(columns=["Shop", "Links Sent", "Online", "Walk-Ins"])

    max_date = df["Date"].max().date()
    min_date = df["Date"].min().date()
    period = resolve_period(period_type, max_date, ref_date)

    cur_df = filter_period(df, period["start"], period["end"])
    prev_df = filter_period(df, period["prev_start"], period["prev_end"])

    cur_kpis = compute_kpis(cur_df)
    prev_kpis = compute_kpis(prev_df)
    evaluated = evaluate_metrics(cur_kpis, prev_kpis)

    meta = {
        "period_type": period_type,
        "period_label": period["label"],
        "date_range": period["date_range"],
        "days": period["days"],
        "generated_on": datetime.now().strftime("%d %b %Y, %H:%M"),
        "compared_to": period["compared_to"],
        # ISO dates so the frontend filter bar can navigate prev/next periods and
        # bound the date picker, without duplicating the day/week/month period
        # math that already lives in periods.py.
        "start": period["start"].isoformat(),
        "end": period["end"].isoformat(),
        "min_date": min_date.isoformat(),
        "max_date": max_date.isoformat(),
    }

    customer_metrics_section = customer_metrics.build_section(cur_df, prev_df, cur_kpis, prev_kpis, period)
    store_section = store_performance.build_section(cur_df, prev_df, period_type, period)
    gender_section = gender_performance.build_section(cur_df, prev_df, period)
    traffic_section = traffic.build_section(footfall_df, footfall_gaps or [], cur_df, period)
    revenue_section = revenue.build_section(df, cur_kpis, prev_kpis, period_type, period)
    data_quality_section = data_quality.build_section(cur_df, prev_df, period)
    feedback_section = feedback.build_section(feedback_daily_df, feedback_by_shop_df, feedback_links_df, period_type, period)

    return {
        "meta": meta,
        "kpi_strip": build_kpi_strip(cur_kpis, prev_kpis, period["compared_to"]),
        "context_note": build_context_note(period, cur_kpis),
        "exec_summary": {
            "narrative": build_narrative(period, cur_kpis, prev_kpis, evaluated),
            "metrics": build_comparison_rows(evaluated),
            "flags": build_flags(evaluated, cur_kpis, period["compared_to"]),
            "meeting_note": build_meeting_note(evaluated, cur_kpis, period),
        },
        "customer_metrics": customer_metrics_section,
        "store_performance": store_section,
        "gender_performance": gender_section,
        "traffic": traffic_section,
        "revenue_analysis": revenue_section,
        "data_quality": data_quality_section,
        "feedback": feedback_section,
        "priorities": priorities.build_section(
            evaluated, store_section, gender_section, traffic_section,
            data_quality_section, feedback_section, customer_metrics_section, period,
        ),
    }
