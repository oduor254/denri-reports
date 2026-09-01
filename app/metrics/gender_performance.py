import pandas as pd

from app.metrics import formatting as fmt

# Fixed display order; "N/A" only appears in the Overall Split (4.1) when it
# actually has rows in the current or previous period (per user request).
# "Corporate" is the sheet's non-individual-customer category (recorded as
# "Organization" on older rows, folded together in app/data/shops.py).
_CATEGORIES = ["Female", "Male", "Corporate", "N/A"]

# Gender by Location (4.2) always shows these three as fixed columns, regardless
# of whether a given period has any Corporate rows - N/A is excluded from
# this table entirely (per user request).
_LOCATION_CATEGORIES = ["Female", "Male", "Corporate"]


def _customer_gender(df: pd.DataFrame) -> pd.Series:
    """One Gender value per unique valid-phone customer (their latest entry in
    the period) - the same customer population nunique(Phone) uses for the
    'Customers' KPI elsewhere, so every gender tally reconciles exactly with
    'Total Customers' instead of counting a repeat visitor's gender once per
    transaction."""
    valid = df[df["Phone Valid"]]
    if valid.empty:
        return pd.Series(dtype=object)
    return valid.sort_values("Date").groupby("Phone").tail(1)["Gender"]


def build_overall_split(cur_df: pd.DataFrame, prev_df: pd.DataFrame) -> list:
    cur_genders = _customer_gender(cur_df)
    prev_genders = _customer_gender(prev_df)
    cur_total = len(cur_genders)
    prev_total = len(prev_genders)
    cur_counts = cur_genders.value_counts()
    prev_counts = prev_genders.value_counts()

    rows = []
    for gender in _CATEGORIES:
        cur_count = int(cur_counts.get(gender, 0))
        prev_count = int(prev_counts.get(gender, 0))
        if gender == "N/A" and cur_count == 0 and prev_count == 0:
            continue

        cur_pct = (cur_count / cur_total * 100) if cur_total else 0.0
        prev_pct = (prev_count / prev_total * 100) if prev_total else 0.0
        change, dir_ = fmt.pp_delta(cur_pct, prev_pct)

        rows.append({
            "gender": gender,
            "count": fmt.count(cur_count),
            "pct": fmt.pct(cur_pct),
            "pct_raw": cur_pct,
            "change": change,
            "change_raw": cur_pct - prev_pct,
            "dir": dir_,
        })
    return rows


def _location_row(shop: str, shop_df: pd.DataFrame) -> dict:
    genders = _customer_gender(shop_df)
    total = len(genders)
    counts = genders.value_counts()
    row = {"shop": shop, "total": fmt.count(total), "total_raw": total}
    for gender in _LOCATION_CATEGORIES:
        key = gender.lower()
        c = int(counts.get(gender, 0))
        pct_val = (c / total * 100) if total else 0.0
        row[key] = fmt.count(c)
        row[f"{key}_pct"] = fmt.pct(pct_val)
        row[f"{key}_raw"] = c
        row[f"{key}_pct_raw"] = pct_val
    return row


def build_by_location(cur_df: pd.DataFrame) -> dict:
    shops = sorted(cur_df["Location"].unique())

    rows = [_location_row(shop, cur_df[cur_df["Location"] == shop]) for shop in shops]
    rows.sort(key=lambda r: r["total_raw"], reverse=True)
    rows.append(_location_row("TOTAL", cur_df))

    return {"columns": _LOCATION_CATEGORIES, "rows": rows}


def build_gender_ratio(overall: list):
    """Overall Female:Male ratio, expressed both ways round so neither reads as
    'the interesting one' - e.g. '1.55 : 1 (Female : Male)'."""
    female = next((r for r in overall if r["gender"] == "Female"), None)
    male = next((r for r in overall if r["gender"] == "Male"), None)
    if not female or not male:
        return None

    female_n = female["pct_raw"]
    male_n = male["pct_raw"]
    if male_n == 0 or female_n == 0:
        return None

    ratio = female_n / male_n
    return {
        "female_pct": female["pct"],
        "male_pct": male["pct"],
        "ratio_text": f"{ratio:.2f} : 1 (Female : Male)" if ratio >= 1 else f"1 : {1 / ratio:.2f} (Female : Male)",
    }


def build_summary(overall: list, by_location: dict, period: dict) -> str:
    leading = max((r for r in overall if r["gender"] != "N/A"), key=lambda r: r["pct_raw"], default=None)
    if not leading:
        return "No gender data available for this period."

    trend_word = {"up": "up", "down": "down", "neutral": "flat"}[leading["dir"]]
    sentences = [
        f"{leading['gender']} customers made up {leading['pct']} of transactions this period "
        f"({trend_word} {leading['change'].split(' ', 1)[1]} vs {period['compared_to']})."
    ]

    other_shares = ", ".join(f"{r['gender']} {r['pct']}" for r in overall if r["gender"] != leading["gender"])
    if other_shares:
        sentences.append(f"Remaining share: {other_shares}.")

    key = leading["gender"].lower()
    shops = [r for r in by_location["rows"] if r["shop"] != "TOTAL" and key in r]
    if shops:
        top_shop = max(shops, key=lambda r: int(r[key].replace(",", "")) / max(int(r["total"].replace(",", "")), 1))
        sentences.append(f"{top_shop['shop']} has the highest concentration of {key} customers.")

    return " ".join(sentences)


def build_meeting_note(overall: list, period: dict) -> str:
    movers = [r for r in overall if abs(r["change_raw"]) >= 3]
    if not movers:
        return f"Gender mix was stable vs {period['compared_to']} - no shifts of note."

    parts = [
        f"{r['gender']} share {'rose' if r['change_raw'] > 0 else 'fell'} "
        f"{abs(r['change_raw']):.1f} pp vs {period['compared_to']}"
        for r in movers
    ]
    return "Notable gender-mix shift: " + "; ".join(parts) + ". Worth a look if unexpected."


def build_section(cur_df: pd.DataFrame, prev_df: pd.DataFrame, period: dict) -> dict:
    overall = build_overall_split(cur_df, prev_df)
    by_location = build_by_location(cur_df)
    return {
        "summary": build_summary(overall, by_location, period),
        "overall": overall,
        "ratio": build_gender_ratio(overall),
        "by_location": by_location,
        "meeting_note": build_meeting_note(overall, period),
    }
