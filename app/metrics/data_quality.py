import pandas as pd

from app.metrics import formatting as fmt

_ROWS = [
    ("Total Records", None),
    ("Valid Phone Numbers", "valid"),
    ("N/A Phones", "na"),
    ("Invalid", "invalid"),
]

# Breakdown of 'Invalid', shown as indented sub-rows beneath it. Each kind needs a
# different fix, and 'too_short' is what the sheet itself counts as "incomplete".
_INVALID_REASONS = [
    ("↳ Incomplete (under 9 digits)", "too_short"),
    ("↳ Wrong prefix (9 digits, not 7/1/6)", "wrong_prefix"),
    ("↳ Extra digit (10 digits, no leading 0)", "too_long"),
    ("↳ Unreadable (e.g. 2.55E+11)", "unreadable"),
]


def _counts(df: pd.DataFrame) -> dict:
    """Customer-level, not transaction-level: a phone number is a real identifier,
    so 'Valid' dedupes by unique phone (reconciles with the Customers KPI elsewhere
    in the report). N/A and Invalid entries can't be reliably deduped - two blank
    or two garbled entries aren't provably the same person - so those are counted
    as individual records instead."""
    valid_df = df[df["Phone KYC"] == "valid"]
    valid = int(valid_df["Phone"].nunique())
    na = int((df["Phone KYC"] == "na").sum())
    invalid = int((df["Phone KYC"] == "invalid").sum())
    counts = {
        "Total Records": valid + na + invalid,
        "valid": valid,
        "na": na,
        "invalid": invalid,
    }
    for _, reason in _INVALID_REASONS:
        counts[reason] = int((df["Phone KYC Issue"] == reason).sum())
    return counts


def _store_number_unique_count(df: pd.DataFrame) -> int:
    """Unique phone numbers among rows flagged Comparison==TRUE (the store's own
    contact number was used in place of the customer's)."""
    flagged = df[df["Comparison"]]
    return int(flagged["Phone"].nunique())


def build_store_number_by_shop(cur_df: pd.DataFrame) -> list:
    flagged = cur_df[cur_df["Comparison"]]
    if flagged.empty:
        return []

    rows = []
    for shop, group in flagged.groupby("Location"):
        rows.append({
            "shop": shop,
            "unique_numbers": fmt.count(group["Phone"].nunique()),
            "occurrences": fmt.count(len(group)),
            "_unique_raw": group["Phone"].nunique(),
        })
    rows.sort(key=lambda r: r["_unique_raw"], reverse=True)
    for r in rows:
        del r["_unique_raw"]
    return rows


def build_comparison_rows(cur_df: pd.DataFrame, prev_df: pd.DataFrame) -> list:
    cur_counts = _counts(cur_df)
    prev_counts = _counts(prev_df)
    cur_total = cur_counts["Total Records"]
    prev_total = prev_counts["Total Records"]

    # Only show breakdown rows that occur in either period, to keep the table short.
    reason_rows = [(label, key) for label, key in _INVALID_REASONS if cur_counts[key] or prev_counts[key]]

    rows = []
    for label, key in _ROWS + reason_rows:
        cur_val = cur_counts["Total Records"] if key is None else cur_counts[key]
        prev_val = prev_counts["Total Records"] if key is None else prev_counts[key]
        cur_pct = (cur_val / cur_total * 100) if cur_total else 0.0
        prev_pct = (prev_val / prev_total * 100) if prev_total else 0.0
        change, dir_ = fmt.combined_delta(cur_val, prev_val, places=0)

        rows.append({
            "metric": label,
            "current": fmt.count(cur_val),
            "current_pct": fmt.pct(cur_pct) if key is not None else "-",
            "previous": fmt.count(prev_val),
            "previous_pct": fmt.pct(prev_pct) if key is not None else "-",
            "change": change,
            "dir": dir_,
        })

    cur_store_numbers = _store_number_unique_count(cur_df)
    prev_store_numbers = _store_number_unique_count(prev_df)
    change, dir_ = fmt.combined_delta(cur_store_numbers, prev_store_numbers, places=0)
    rows.append({
        "metric": "Store Number Used (unique)",
        "current": fmt.count(cur_store_numbers),
        "current_pct": fmt.pct(cur_store_numbers / cur_total * 100) if cur_total else "-",
        "previous": fmt.count(prev_store_numbers),
        "previous_pct": fmt.pct(prev_store_numbers / prev_total * 100) if prev_total else "-",
        "change": change,
        "dir": dir_,
    })

    return rows


def build_score_note(cur_df: pd.DataFrame) -> str:
    counts = _counts(cur_df)
    total = counts["Total Records"]
    score = (counts["valid"] / total * 100) if total else 0.0

    if score >= 95:
        verdict = "Excellent"
    elif score >= 90:
        verdict = "Good"
    elif score >= 80:
        verdict = "Fair"
    else:
        verdict = "Needs attention"

    note = f"KYC health score: {fmt.pct(score)} of records have a valid phone number ({verdict})."
    if counts["invalid"] > 0:
        invalid_share = counts["invalid"] / total * 100 if total else 0.0
        note += f" {fmt.count(counts['invalid'])} record(s) ({fmt.pct(invalid_share)}) have an unrecognized phone format worth cleaning up."
    return note


def build_summary(cur_df: pd.DataFrame, prev_df: pd.DataFrame, period: dict) -> str:
    cur_counts = _counts(cur_df)
    prev_counts = _counts(prev_df)
    cur_total = cur_counts["Total Records"]
    prev_total = prev_counts["Total Records"]

    cur_score = (cur_counts["valid"] / cur_total * 100) if cur_total else 0.0
    prev_score = (prev_counts["valid"] / prev_total * 100) if prev_total else 0.0
    pp_diff = cur_score - prev_score
    dir_ = fmt.direction(pp_diff)
    trend_word = {"up": "up", "down": "down", "neutral": "flat"}[dir_]

    sentence = (
        f"Of {fmt.count(cur_total)} records this period, {fmt.pct(cur_score)} carry a valid phone number "
        f"({trend_word} {abs(pp_diff):.1f} pp vs {period['compared_to']}). "
        f"{fmt.count(cur_counts['na'])} are unrecorded (N/A) and {fmt.count(cur_counts['invalid'])} don't "
        f"match a recognized phone format."
    )

    store_numbers = _store_number_unique_count(cur_df)
    if store_numbers > 0:
        sentence += f" {fmt.count(store_numbers)} unique instance(s) used the shop's own number instead of the customer's."

    return sentence


def build_meeting_note(cur_df: pd.DataFrame, store_number_by_shop: list, period: dict) -> str:
    counts = _counts(cur_df)
    total = counts["Total Records"]
    invalid_share = (counts["invalid"] / total * 100) if total else 0.0
    na_share = (counts["na"] / total * 100) if total else 0.0

    sentences = []
    if invalid_share >= 2:
        sentences.append(
            f"Invalid phone entries are at {fmt.pct(invalid_share)} - flag with store teams to "
            "re-capture customer numbers at checkout."
        )
    if na_share >= 2:
        sentences.append(f"{fmt.pct(na_share)} of records have no phone captured at all - review data entry process.")

    if store_number_by_shop:
        shop_list = ", ".join(f"{r['shop']} ({r['unique_numbers']})" for r in store_number_by_shop)
        sentences.append(f"Shop's own number used in place of a customer's at: {shop_list} - remind staff to capture the actual customer number.")

    if not sentences:
        sentences.append(f"Phone capture quality was healthy vs {period['compared_to']} - no escalations needed.")

    return " ".join(sentences)


def build_section(cur_df: pd.DataFrame, prev_df: pd.DataFrame, period: dict) -> dict:
    store_number_by_shop = build_store_number_by_shop(cur_df)
    return {
        "summary": build_summary(cur_df, prev_df, period),
        "comparison": build_comparison_rows(cur_df, prev_df),
        "store_number_by_shop": store_number_by_shop,
        "score_note": build_score_note(cur_df),
        "meeting_note": build_meeting_note(cur_df, store_number_by_shop, period),
    }
