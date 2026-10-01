from datetime import date

import pandas as pd

from app.metrics import formatting as fmt


def _gap_overlaps(gap: dict, start: date, end: date) -> bool:
    gap_after = gap["after"] or date.min
    gap_before = gap["before"] or date.max
    return gap_after < end and gap_before > start


def build_data_gap_note(gaps: list, start: date, end: date):
    overlapping = [g for g in gaps if _gap_overlaps(g, start, end)]
    if not overlapping:
        return None

    parts = []
    for g in overlapping:
        if g["after"] and g["before"]:
            parts.append(f"{g['days']} day(s) between {g['after']:%d %b} and {g['before']:%d %b}")
        elif g["before"]:
            parts.append(f"{g['days']} day(s) before {g['before']:%d %b}")
        elif g["after"]:
            parts.append(f"{g['days']} day(s) after {g['after']:%d %b}")
        else:
            parts.append(f"{g['days']} day(s) of unlabeled data")

    return (
        "Footfall sheet has unlabeled/unresolved day-block(s) overlapping this period: "
        + "; ".join(parts) + ". Those days are excluded from the totals below rather than guessed."
    )


def build_anomaly_note(anomalies: list, start: date, end: date):
    in_period = [a for a in anomalies if start <= a["date"] <= end]
    if not in_period:
        return None

    parts = [
        f"{a['shop']} {a['date']:%d %b}: {a['field']} = {a['value']} (cell {a['cell']})"
        for a in sorted(in_period, key=lambda a: (a["date"], a["shop"]))
    ]
    return (
        "Footfall sheet has impossible negative counts this period: " + "; ".join(parts)
        + ". They're included as entered so totals match the sheet - correct the cell(s) at source."
    )


def build_rows(footfall_period_df: pd.DataFrame, cur_shops_df: pd.DataFrame) -> list:
    # Walk-in Purchased/Total/Conv. Rate come from the Footfall sheet, which has
    # no customer identity at all (it's a door-tally, not a transaction log) -
    # there's no "unique" version of a walk-in count to compute. Online/
    # Activation/Total Customers come from Shops (which has Phone) and are
    # deduped to unique customers, same as everywhere else in the app.
    shops = sorted(footfall_period_df["Shop"].unique())
    rows = []

    for shop in shops:
        shop_footfall = footfall_period_df[footfall_period_df["Shop"] == shop]
        purchased = int(shop_footfall["Walkins Purchased"].sum())
        not_purchased = int(shop_footfall["Walkins Not Purchased"].sum())
        total_walkins = purchased + not_purchased
        conv_rate = (purchased / total_walkins * 100) if total_walkins else 0.0

        shop_sales = cur_shops_df[cur_shops_df["Location"] == shop]
        valid_sales = shop_sales[shop_sales["Phone Valid"]]
        online = valid_sales[valid_sales["Customer Type"] == "online"]["Phone"].nunique()
        activation = valid_sales[valid_sales["Customer Type"] == "activation"]["Phone"].nunique()
        total_customers = valid_sales["Phone"].nunique()

        rows.append({
            "shop": shop,
            "walkin_purchased": fmt.count(purchased),
            "walkin_total": fmt.count(total_walkins),
            "conv_rate": fmt.pct(conv_rate),
            "online": fmt.count(online),
            "activation": fmt.count(activation),
            "total_customers": fmt.count(total_customers),
            # Raw numeric values so the frontend can sort columns without
            # re-parsing display text.
            "walkin_purchased_raw": purchased,
            "walkin_total_raw": total_walkins,
            "conv_rate_raw": conv_rate,
            "online_raw": online,
            "activation_raw": activation,
            "total_customers_raw": total_customers,
        })

    rows.sort(key=lambda r: r["walkin_total_raw"], reverse=True)

    total_purchased = int(footfall_period_df["Walkins Purchased"].sum())
    total_not_purchased = int(footfall_period_df["Walkins Not Purchased"].sum())
    total_walkins_all = total_purchased + total_not_purchased
    total_conv_rate = (total_purchased / total_walkins_all * 100) if total_walkins_all else 0.0

    physical_sales = cur_shops_df[cur_shops_df["Location"].isin(shops)]
    valid_physical_sales = physical_sales[physical_sales["Phone Valid"]]
    total_online = valid_physical_sales[valid_physical_sales["Customer Type"] == "online"]["Phone"].nunique()
    total_activation = valid_physical_sales[valid_physical_sales["Customer Type"] == "activation"]["Phone"].nunique()
    total_customers_all = valid_physical_sales["Phone"].nunique()

    rows.append({
        "shop": "TOTAL",
        "walkin_purchased": fmt.count(total_purchased),
        "walkin_total": fmt.count(total_walkins_all),
        "conv_rate": fmt.pct(total_conv_rate),
        "online": fmt.count(total_online),
        "activation": fmt.count(total_activation),
        "total_customers": fmt.count(total_customers_all),
        "walkin_purchased_raw": total_purchased,
        "walkin_total_raw": total_walkins_all,
        "conv_rate_raw": total_conv_rate,
        "online_raw": total_online,
        "activation_raw": total_activation,
        "total_customers_raw": total_customers_all,
    })

    return rows


def build_summary(rows: list, period: dict) -> str:
    total = next((r for r in rows if r["shop"] == "TOTAL"), None)
    shops = [r for r in rows if r["shop"] != "TOTAL"]
    if not total or not shops:
        return "No foot traffic data available for this period."

    sentences = [
        f"Across {len(shops)} physical stores, {total['walkin_total']} walk-ins were recorded this period "
        f"with a {total['conv_rate']} overall conversion rate, alongside {total['online']} unique online and "
        f"{total['activation']} unique activation customers."
    ]

    with_traffic = [r for r in shops if r["walkin_total_raw"] > 0]
    if with_traffic:
        best = max(with_traffic, key=lambda r: r["conv_rate_raw"])
        worst = min(with_traffic, key=lambda r: r["conv_rate_raw"])
        if best["shop"] != worst["shop"]:
            sentences.append(f"{best['shop']} converted best at {best['conv_rate']}, while {worst['shop']} lagged at {worst['conv_rate']}.")

    return " ".join(sentences)


def build_meeting_note(rows: list, data_gap_note, data_anomaly_note, period: dict) -> str:
    shops = [r for r in rows if r["shop"] != "TOTAL" and r["walkin_total_raw"] > 0]
    sentences = []

    if shops:
        worst = min(shops, key=lambda r: r["conv_rate_raw"])
        if worst["conv_rate_raw"] < 50:
            sentences.append(f"{worst['shop']}'s conversion rate ({worst['conv_rate']}) is worth investigating with the store team.")

    if data_gap_note:
        sentences.append("Footfall data has gaps this period (see callout above) - confirm daily entry is happening consistently.")

    if data_anomaly_note:
        sentences.append("Some footfall entries are negative (see callout above) - ask the shops concerned to re-check their daily totals.")

    if not sentences:
        sentences.append(f"Conversion rates were healthy across stores vs {period['compared_to']} - no escalations needed.")

    return " ".join(sentences)


def build_section(footfall_df: pd.DataFrame, gaps: list, cur_shops_df: pd.DataFrame, period: dict, anomalies: list = None) -> dict:
    start, end = period["start"], period["end"]

    if footfall_df.empty:
        footfall_period_df = footfall_df
    else:
        dates = footfall_df["Date"].dt.date
        footfall_period_df = footfall_df[(dates >= start) & (dates <= end)]

    data_gap_note = build_data_gap_note(gaps, start, end)
    data_anomaly_note = build_anomaly_note(anomalies or [], start, end)
    rows = build_rows(footfall_period_df, cur_shops_df)

    return {
        "summary": build_summary(rows, period),
        "data_gap_note": data_gap_note,
        "data_anomaly_note": data_anomaly_note,
        "rows": rows,
        "meeting_note": build_meeting_note(rows, data_gap_note, data_anomaly_note, period),
    }
