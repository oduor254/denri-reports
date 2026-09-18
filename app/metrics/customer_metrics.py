import pandas as pd

from app.metrics import formatting as fmt

CHANNELS = [("Walk-in", "walkin"), ("Online", "online"), ("Activation", "activation")]

_FREQUENCY_READS = {
    "1 Purchase": "Primary re-engagement pool",
    "2 Purchases": "Early-loyalty tier",
    "3-5 Purchases": "Loyalty escalation target",
    "6+ Purchases": "VIP cohort",
}


def _products_per_customer(df: pd.DataFrame) -> pd.Series:
    """Total product units (summed Quantity, not transaction count or visit
    days) per unique valid-phone customer in the period - a customer who buys
    3 units in one transaction bought '3 products', same as one who bought 1
    unit on 3 separate visits. Quantity is usually 1 per line but not always
    (bulk/wholesale rows exist), so summing is the correct 'how many products
    did they buy' answer, not counting rows."""
    valid = df[df["Phone Valid"]]
    if valid.empty:
        return pd.Series(dtype=float)
    return valid.groupby("Phone")["Quantity"].sum()


def build_comparison_rows(cur_kpis: dict, prev_kpis: dict) -> list:
    rows = []

    for label, key in (
        ("Total Customers", "Customers"),
        ("New Customers", "New"),
        ("Repeat Customers", "Repeat"),
    ):
        current, previous = cur_kpis[key], prev_kpis[key]
        change, dir_ = fmt.combined_delta(current, previous, places=0)
        rows.append({
            "metric": label, "current": fmt.count(current), "previous": fmt.count(previous),
            "change": change, "dir": dir_,
        })

    current, previous = cur_kpis["Repeat Rate"], prev_kpis["Repeat Rate"]
    change, dir_ = fmt.pp_delta(current, previous)
    rows.append({
        "metric": "Repeat Customer Rate", "current": fmt.pct(current), "previous": fmt.pct(previous),
        "change": change, "dir": dir_,
    })

    current, previous = cur_kpis["Avg Orders"], prev_kpis["Avg Orders"]
    change, dir_ = fmt.combined_delta(current, previous, places=2)
    rows.append({
        "metric": "Avg Orders / Customer", "current": fmt.decimal(current, 2),
        "previous": fmt.decimal(previous, 2), "change": change, "dir": dir_,
    })

    return rows


def build_frequency_distribution(cur_df: pd.DataFrame) -> list:
    products = _products_per_customer(cur_df)
    total = len(products)

    bands = [
        ("1 Purchase", products == 1),
        ("2 Purchases", products == 2),
        ("3-5 Purchases", (products >= 3) & (products <= 5)),
        ("6+ Purchases", products >= 6),
    ]

    rows = []
    for label, mask in bands:
        count = int(mask.sum())
        pct_val = (count / total * 100) if total else 0.0
        rows.append({
            "band": label,
            "count": fmt.count(count),
            "pct": fmt.pct(pct_val),
            "read": _FREQUENCY_READS[label],
        })
    return rows


def build_channel_overview(cur_df: pd.DataFrame) -> list:
    """Distribution by unique customer (dedup by valid Phone), not transaction
    count - matches the 'Total Customers' KPI elsewhere, so this table's TOTAL
    row reconciles with it instead of showing a larger, transaction-inflated
    figure. Avg Spend stays a per-transaction average (a distinct, deliberately
    different metric from per-customer spend used elsewhere)."""
    valid = cur_df[cur_df["Phone Valid"]]
    total_customers = valid["Phone"].nunique()
    total_txn = len(cur_df)
    rows = []

    for label, key in CHANNELS:
        channel_df = cur_df[cur_df["Customer Type"] == key]
        customers = channel_df[channel_df["Phone Valid"]]["Phone"].nunique()
        share = (customers / total_customers * 100) if total_customers else 0.0
        avg_spend = float(channel_df["Total"].mean()) if not channel_df.empty else 0.0
        rows.append({
            "channel": label, "customers": fmt.count(customers), "share": fmt.pct(share),
            "avg_spend": fmt.money(avg_spend), "_avg_spend_raw": avg_spend, "_customers_raw": customers,
        })

    tagged = sum(r["_customers_raw"] for r in rows)
    untagged_customers = total_customers - tagged
    if untagged_customers > 0:
        untagged_df = cur_df[~cur_df["Customer Type"].isin([key for _, key in CHANNELS])]
        untagged_share = (untagged_customers / total_customers * 100) if total_customers else 0.0
        avg_spend = float(untagged_df["Total"].mean()) if not untagged_df.empty else 0.0
        rows.append({
            "channel": "Untagged / Other", "customers": fmt.count(untagged_customers),
            "share": fmt.pct(untagged_share), "avg_spend": fmt.money(avg_spend),
            "_avg_spend_raw": avg_spend, "_customers_raw": untagged_customers,
        })

    tagged_rows = [r for r in rows if r["channel"] != "Untagged / Other" and r["_customers_raw"] > 0]
    best = max(tagged_rows, key=lambda r: r["_avg_spend_raw"], default=None)

    for r in rows:
        note = ""
        if best is not None and r is best:
            note = "Highest avg spend"
        elif r["channel"] == "Untagged / Other" and total_customers and r["_customers_raw"] / total_customers > 0.10:
            note = "Needs Customer Type tagging"
        r["note"] = note
        del r["_avg_spend_raw"]
        del r["_customers_raw"]

    total_revenue = float(cur_df["Total"].sum())
    avg_spend_total = (total_revenue / total_txn) if total_txn else 0.0
    rows.append({
        "channel": "TOTAL", "customers": fmt.count(total_customers), "share": "100.0%",
        "avg_spend": fmt.money(avg_spend_total), "note": "",
    })

    return rows


def build_summary(cur_kpis: dict, prev_kpis: dict, frequency: list, channels: list, period: dict) -> str:
    pp_diff = cur_kpis["Repeat Rate"] - prev_kpis["Repeat Rate"]
    dir_ = fmt.direction(pp_diff)
    trend_word = {"up": "up", "down": "down", "neutral": "flat"}[dir_]

    sentences = [
        f"{fmt.count(cur_kpis['Customers'])} customers were served this period "
        f"({fmt.count(cur_kpis['New'])} new, {fmt.count(cur_kpis['Repeat'])} repeat), a repeat rate of "
        f"{fmt.pct(cur_kpis['Repeat Rate'])} ({trend_word} {abs(pp_diff):.1f} pp vs {period['compared_to']})."
    ]

    one_purchase = next((b for b in frequency if b["band"] == "1 Purchase"), None)
    if one_purchase:
        sentences.append(f"{one_purchase['pct']} of customers made just one purchase this period.")

    tagged = [c for c in channels if c["channel"] not in ("Untagged / Other", "TOTAL")]
    leading = max(tagged, key=lambda c: float(c["share"].rstrip("%")), default=None)
    if leading:
        sentences.append(f"{leading['channel']} led with {leading['share']} of customers this period.")

    return " ".join(sentences)


def build_meeting_note(cur_kpis: dict, prev_kpis: dict, channels: list, period: dict) -> str:
    rr_change, rr_dir = fmt.pp_delta(cur_kpis["Repeat Rate"], prev_kpis["Repeat Rate"])
    rr_word = {"up": "improved", "down": "declined", "neutral": "held steady"}[rr_dir]

    tagged_channel_rows = [r for r in channels if r["channel"] not in ("Untagged / Other", "TOTAL")]
    leading = max(tagged_channel_rows, key=lambda r: float(r["share"].rstrip("%")), default=None)

    sentences = [f"Repeat customer rate {rr_word} vs {period['compared_to']} ({rr_change.split(' ', 1)[1]})."]
    if leading:
        sentences.append(f"{leading['channel']} remains the leading tagged channel at {leading['share']} of customers.")

    untagged = next((r for r in channels if r["channel"] == "Untagged / Other"), None)
    if untagged and untagged["note"]:
        sentences.append(f"{untagged['share']} of orders this period have no Customer Type tag — worth chasing with store teams.")

    return " ".join(sentences)


def build_section(cur_df: pd.DataFrame, prev_df: pd.DataFrame, cur_kpis: dict, prev_kpis: dict, period: dict) -> dict:
    channels = build_channel_overview(cur_df)
    frequency = build_frequency_distribution(cur_df)
    return {
        "summary": build_summary(cur_kpis, prev_kpis, frequency, channels, period),
        "comparison": build_comparison_rows(cur_kpis, prev_kpis),
        "frequency": frequency,
        "channels": channels,
        "meeting_note": build_meeting_note(cur_kpis, prev_kpis, channels, period),
    }
