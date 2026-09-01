import pandas as pd

from app.metrics import formatting as fmt
from app.metrics.customer_metrics import CHANNELS


def _money_delta(current: float, previous: float):
    """'<glyph> <signed KES diff>' - the Store Performance table keeps Change and
    Change % as separate columns (per spec), so this carries a currency prefix but
    no embedded percentage (unlike fmt.combined_delta, which reads as a bare count
    and would be wrong for a revenue delta)."""
    diff = current - previous
    dir_ = fmt.direction(diff)
    sign = "+" if diff >= 0 else "-"
    return f"{fmt.glyph(dir_)} {sign}KES {abs(diff):,.2f}", dir_


def _repeat_count(df: pd.DataFrame) -> int:
    """Customers who visited THIS shop on 2+ distinct days in the period (per-store
    repeat, independent of whether they also shopped at other locations)."""
    valid = df[df["Phone Valid"]]
    if valid.empty:
        return 0
    visit_days = valid.groupby("Phone")["Date"].nunique()
    return int((visit_days >= 2).sum())


def build_rows(cur_df: pd.DataFrame, prev_df: pd.DataFrame) -> list:
    shops = sorted(set(cur_df["Location"]) | set(prev_df["Location"]))
    rows = []

    for shop in shops:
        cur_shop = cur_df[cur_df["Location"] == shop]
        prev_shop = prev_df[prev_df["Location"] == shop]

        current = float(cur_shop["Total"].sum())
        previous = float(prev_shop["Total"].sum())
        change, dir_ = _money_delta(current, previous)
        pc = fmt.pct_change(current, previous)
        change_pct = f"{pc:+.1f}%" if pc is not None else "n/a"

        customers = cur_shop[cur_shop["Phone Valid"]]["Phone"].nunique()
        repeat = _repeat_count(cur_shop)
        new = int(customers - repeat)
        repeat_rate = (repeat / customers * 100) if customers else 0.0

        rows.append({
            "shop": shop,
            "current": fmt.money(current),
            "previous": fmt.money(previous),
            "change": change,
            "change_pct": change_pct,
            "dir": dir_,
            "new": fmt.count(new),
            "repeat": fmt.count(repeat),
            "repeat_rate": fmt.pct(repeat_rate),
            # Raw numeric values alongside the formatted strings above, so the
            # frontend can sort columns without re-parsing display text.
            "current_raw": current,
            "previous_raw": previous,
            "change_raw": current - previous,
            "change_pct_raw": pc,
            "new_raw": new,
            "repeat_raw": repeat,
            "repeat_rate_raw": repeat_rate,
        })

    rows.sort(key=lambda r: r["current_raw"], reverse=True)

    total_current = float(cur_df["Total"].sum())
    total_previous = float(prev_df["Total"].sum())
    total_change, total_dir = _money_delta(total_current, total_previous)
    total_pc = fmt.pct_change(total_current, total_previous)
    total_customers = cur_df[cur_df["Phone Valid"]]["Phone"].nunique()
    total_repeat = _repeat_count(cur_df)
    total_repeat_rate = (total_repeat / total_customers * 100) if total_customers else 0.0

    rows.append({
        "shop": "TOTAL",
        "current": fmt.money(total_current),
        "previous": fmt.money(total_previous),
        "change": total_change,
        "change_pct": f"{total_pc:+.1f}%" if total_pc is not None else "n/a",
        "dir": total_dir,
        "new": fmt.count(total_customers - total_repeat),
        "repeat": fmt.count(total_repeat),
        "repeat_rate": fmt.pct(total_repeat_rate),
        "current_raw": total_current,
        "previous_raw": total_previous,
        "change_raw": total_current - total_previous,
        "change_pct_raw": total_pc,
        "new_raw": total_customers - total_repeat,
        "repeat_raw": total_repeat,
        "repeat_rate_raw": total_repeat_rate,
    })

    return rows


def build_summary(rows: list, channel_mix: list, period: dict) -> str:
    total = next(r for r in rows if r["shop"] == "TOTAL")
    shops = [r for r in rows if r["shop"] != "TOTAL"]
    trend_word = {"up": "grew", "down": "declined", "neutral": "was flat"}[total["dir"]]

    sentences = [
        f"Total store revenue {trend_word} to {total['current']} vs {period['compared_to']} "
        f"({total['change_pct']})."
    ]

    movers = [r for r in shops if r["change_pct_raw"] is not None]
    if movers:
        best = max(movers, key=lambda r: r["change_pct_raw"])
        worst = min(movers, key=lambda r: r["change_pct_raw"])
        if best["shop"] != worst["shop"]:
            best_word = "up" if best["change_pct_raw"] >= 0 else "down"
            worst_word = "up" if worst["change_pct_raw"] >= 0 else "down"
            sentences.append(
                f"{best['shop']} led ({best_word} {abs(best['change_pct_raw']):.1f}%), while {worst['shop']} "
                f"trailed ({worst_word} {abs(worst['change_pct_raw']):.1f}%)."
            )

    mix_shops = [r for r in channel_mix if r["shop"] != "TOTAL"]
    if mix_shops:
        most_online = max(mix_shops, key=lambda r: float(r["online_pct"].rstrip("%")))
        sentences.append(f"{most_online['shop']} has the highest online order share at {most_online['online_pct']}.")

    return " ".join(sentences)


def build_meeting_note(rows: list, period: dict) -> str:
    shops = [r for r in rows if r["shop"] != "TOTAL" and r["change_pct_raw"] is not None]
    if not shops:
        return "No store-level outliers requiring escalation this period."

    worst = min(shops, key=lambda r: r["change_pct_raw"])
    best = max(shops, key=lambda r: r["change_pct_raw"])

    sentences = []
    if worst["change_pct_raw"] <= -10:
        sentences.append(f"Review {worst['shop']}'s performance with the store team ({worst['change_pct']} vs {period['compared_to']}).")
    if best["change_pct_raw"] >= 10 and best["shop"] != worst["shop"]:
        sentences.append(f"Identify what's driving {best['shop']}'s growth ({best['change_pct']}) so it can be replicated elsewhere.")

    if not sentences:
        sentences.append("Store performance was broadly in line with the prior period - no escalations needed.")

    return " ".join(sentences)


def _channel_counts(df: pd.DataFrame) -> dict:
    """Unique customers per channel (dedup by valid Phone), not transaction
    counts - a customer with 3 walk-in visits counts once. A customer tagged
    under more than one channel in the same period counts in each (rare, but
    real), so the three channels aren't guaranteed to sum to 'total'."""
    valid = df[df["Phone Valid"]]
    counts = {label: valid[valid["Customer Type"] == key]["Phone"].nunique() for label, key in CHANNELS}
    counts["total"] = valid["Phone"].nunique()
    return counts


def _channel_sales(df: pd.DataFrame) -> dict:
    """Sales value (KES) per channel - every matching transaction's Total,
    not deduped by customer, since revenue counts every purchase (unlike the
    customer counts above, where a repeat visit shouldn't double-count the
    person)."""
    sales = {label: float(df[df["Customer Type"] == key]["Total"].sum()) for label, key in CHANNELS}
    sales["total"] = float(df["Total"].sum())
    return sales


def build_channel_mix_by_location(cur_df: pd.DataFrame) -> list:
    shops = sorted(cur_df["Location"].unique())
    rows = []

    for shop in shops:
        shop_df = cur_df[cur_df["Location"] == shop]
        counts = _channel_counts(shop_df)
        sales = _channel_sales(shop_df)
        online_pct = (counts["Online"] / counts["total"] * 100) if counts["total"] else 0.0
        rows.append({
            "shop": shop,
            "walkin": fmt.count(counts["Walk-in"]),
            "walkin_sales": fmt.money(sales["Walk-in"]),
            "online": fmt.count(counts["Online"]),
            "online_sales": fmt.money(sales["Online"]),
            "activation": fmt.count(counts["Activation"]),
            "activation_sales": fmt.money(sales["Activation"]),
            "total": fmt.count(counts["total"]),
            "total_sales": fmt.money(sales["total"]),
            "online_pct": fmt.pct(online_pct),
            "_total_raw": counts["total"],
            "walkin_sales_raw": sales["Walk-in"],
            "online_sales_raw": sales["Online"],
            "activation_sales_raw": sales["Activation"],
            "total_sales_raw": sales["total"],
        })

    rows.sort(key=lambda r: r["_total_raw"], reverse=True)
    for r in rows:
        del r["_total_raw"]

    grand = _channel_counts(cur_df)
    grand_sales = _channel_sales(cur_df)
    grand_online_pct = (grand["Online"] / grand["total"] * 100) if grand["total"] else 0.0
    rows.append({
        "shop": "TOTAL",
        "walkin": fmt.count(grand["Walk-in"]),
        "walkin_sales": fmt.money(grand_sales["Walk-in"]),
        "online": fmt.count(grand["Online"]),
        "online_sales": fmt.money(grand_sales["Online"]),
        "activation": fmt.count(grand["Activation"]),
        "activation_sales": fmt.money(grand_sales["Activation"]),
        "total": fmt.count(grand["total"]),
        "total_sales": fmt.money(grand_sales["total"]),
        "online_pct": fmt.pct(grand_online_pct),
        "walkin_sales_raw": grand_sales["Walk-in"],
        "online_sales_raw": grand_sales["Online"],
        "activation_sales_raw": grand_sales["Activation"],
        "total_sales_raw": grand_sales["total"],
    })

    return rows


def _shop_customer_set(df: pd.DataFrame, shop: str) -> set:
    sub = df[(df["Location"] == shop) & (df["Phone Valid"])]
    return set(sub["Phone"].unique())


def build_monthly_retention(cur_df: pd.DataFrame, prev_df: pd.DataFrame) -> list:
    """Month-only: distinguishes 'Repeat' (2+ visits within THIS month - a
    frequency measure) from 'Retention' (bought last month AND bought again
    this month - a continuity measure). Both are scoped per-shop, matching how
    Repeat already works elsewhere in this table."""
    shops = sorted(set(cur_df["Location"]) | set(prev_df["Location"]))
    rows = []

    for shop in shops:
        cur_customers = _shop_customer_set(cur_df, shop)
        prev_customers = _shop_customer_set(prev_df, shop)
        cur_count, prev_count = len(cur_customers), len(prev_customers)
        change, dir_ = fmt.combined_delta(cur_count, prev_count, places=0)

        repeat = _repeat_count(cur_df[cur_df["Location"] == shop])
        repeat_rate = (repeat / cur_count * 100) if cur_count else 0.0

        retained = len(cur_customers & prev_customers)
        retention_rate = (retained / prev_count * 100) if prev_count else 0.0

        rows.append({
            "shop": shop,
            "current": fmt.count(cur_count),
            "previous": fmt.count(prev_count),
            "change": change,
            "dir": dir_,
            "repeat": fmt.count(repeat),
            "repeat_rate": fmt.pct(repeat_rate),
            "retention": fmt.count(retained),
            "retention_rate": fmt.pct(retention_rate),
            "current_raw": cur_count,
            "previous_raw": prev_count,
            "change_raw": cur_count - prev_count,
            "repeat_raw": repeat,
            "repeat_rate_raw": repeat_rate,
            "retention_raw": retained,
            "retention_rate_raw": retention_rate,
        })

    rows.sort(key=lambda r: r["current_raw"], reverse=True)

    total_cur_customers = set(cur_df[cur_df["Phone Valid"]]["Phone"].unique())
    total_prev_customers = set(prev_df[prev_df["Phone Valid"]]["Phone"].unique())
    total_cur_count, total_prev_count = len(total_cur_customers), len(total_prev_customers)
    total_change, total_dir = fmt.combined_delta(total_cur_count, total_prev_count, places=0)

    total_repeat = _repeat_count(cur_df)
    total_repeat_rate = (total_repeat / total_cur_count * 100) if total_cur_count else 0.0
    total_retained = len(total_cur_customers & total_prev_customers)
    total_retention_rate = (total_retained / total_prev_count * 100) if total_prev_count else 0.0

    rows.append({
        "shop": "TOTAL",
        "current": fmt.count(total_cur_count),
        "previous": fmt.count(total_prev_count),
        "change": total_change,
        "dir": total_dir,
        "repeat": fmt.count(total_repeat),
        "repeat_rate": fmt.pct(total_repeat_rate),
        "retention": fmt.count(total_retained),
        "retention_rate": fmt.pct(total_retention_rate),
        "current_raw": total_cur_count,
        "previous_raw": total_prev_count,
        "change_raw": total_cur_count - total_prev_count,
        "repeat_raw": total_repeat,
        "repeat_rate_raw": total_repeat_rate,
        "retention_raw": total_retained,
        "retention_rate_raw": total_retention_rate,
    })

    return rows


def build_section(cur_df: pd.DataFrame, prev_df: pd.DataFrame, period_type: str, period: dict) -> dict:
    rows = build_rows(cur_df, prev_df)
    channel_mix = build_channel_mix_by_location(cur_df)
    monthly_retention = build_monthly_retention(cur_df, prev_df) if period_type == "month" else None
    return {
        "summary": build_summary(rows, channel_mix, period),
        "rows": rows,
        "channel_mix": channel_mix,
        "monthly_retention": monthly_retention,
        "meeting_note": build_meeting_note(rows, period),
    }
