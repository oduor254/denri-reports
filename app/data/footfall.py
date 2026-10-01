"""Parser for the 'Footfall' sheet, a wide matrix rather than a plain table.

Structure (verified directly against the live sheet - see plan notes):
  - Row 2 is the reliable anchor: every block is exactly 4 columns wide and always
    reads WALKINS PURCHASED, W.NOT PURCHASED, TOTAL, C. RATE.
  - Row 1 holds the block's label (a date, 'WEEK N', or 'MONTHLY') but it is NOT
    aligned to the block's first column - it sits somewhere within the block's
    4-column span. Block boundaries must come from row 2, not row 1.
  - Some day-blocks have no label at all (row 1 blank across the whole span). These
    are inferred as the missing sequential date between two known dated blocks;
    if that can't be resolved cleanly, the run is recorded as an unresolved gap
    instead of guessed.
  - WEEK N / MONTHLY blocks are the sheet's own rollups and are skipped - period
    aggregates are recomputed from the daily blocks for consistency with the rest
    of the app.
  - Negative counts (e.g. W.NOT PURCHASED = -3, where a shop entered a TOTAL lower
    than its purchases) are kept as-is so totals reconcile with the sheet's own
    rollups, and are reported as anomalies so the bad cell can be fixed at source.
"""
import re
import threading
import time
from datetime import datetime, timedelta

import pandas as pd

from app.config import Config
from app.sheets_client import get_worksheet_values

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_lock = threading.Lock()
_cache = {"fetched_at": 0.0, "df": None, "gaps": None, "anomalies": None}


def _find_block_labels(row1: list, row2: list) -> list:
    """Returns a list of {start, kind, date} for every 4-col block, in column order.
    kind is 'date' | 'rollup' | 'blank' (blank = no label found in row 1)."""
    starts = [i for i, v in enumerate(row2) if v.strip().upper() == "WALKINS PURCHASED"]
    blocks = []
    for start in starts:
        label = None
        for j in range(start, min(start + 4, len(row1))):
            if row1[j].strip():
                label = row1[j].strip()
                break
        if label is None:
            blocks.append({"start": start, "kind": "blank", "date": None})
        elif _DATE_RE.match(label):
            blocks.append({"start": start, "kind": "date", "date": datetime.strptime(label, "%d/%m/%Y").date()})
        else:
            blocks.append({"start": start, "kind": "rollup", "date": None})
    return blocks


def _resolve_blank_runs(blocks: list) -> list:
    """Fills in sequential dates for blank runs bounded by two dated blocks whose
    day-gap exactly matches the run length. Unresolvable runs stay 'blank' - the
    caller records those as data gaps rather than guessing."""
    i, n = 0, len(blocks)
    while i < n:
        if blocks[i]["kind"] != "blank":
            i += 1
            continue
        j = i
        while j < n and blocks[j]["kind"] == "blank":
            j += 1
        if i > 0 and blocks[i - 1]["kind"] == "date" and j < n and blocks[j]["kind"] == "date":
            start_date = blocks[i - 1]["date"]
            end_date = blocks[j]["date"]
            expected_days = (end_date - start_date).days - 1
            if expected_days == (j - i):
                for k in range(i, j):
                    blocks[k]["kind"] = "date"
                    blocks[k]["date"] = start_date + timedelta(days=(k - i + 1))
        i = j
    return blocks


def _int(v: str) -> int:
    v = v.strip().replace(",", "")
    return int(v) if re.fullmatch(r"-?\d+", v) else 0


def _cell_ref(row_idx: int, col_idx: int) -> str:
    """0-based (row, col) -> A1 reference, e.g. (16, 1188) -> 'ATG17'."""
    letters = ""
    col = col_idx + 1
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row_idx + 1}"


def _parse_footfall(values: list):
    row1, row2 = values[0], values[1]
    blocks = _resolve_blank_runs(_find_block_labels(row1, row2))
    date_blocks = [b for b in blocks if b["kind"] == "date"]

    # Unresolved gaps: bounded by the nearest 'date' blocks on either side (if any),
    # recorded as (bounding_start, bounding_end, num_unresolved_days).
    gaps = []
    i, n = 0, len(blocks)
    while i < n:
        if blocks[i]["kind"] == "blank":
            j = i
            while j < n and blocks[j]["kind"] == "blank":
                j += 1
            prev_date = blocks[i - 1]["date"] if i > 0 and blocks[i - 1]["kind"] == "date" else None
            next_date = blocks[j]["date"] if j < n and blocks[j]["kind"] == "date" else None
            gaps.append({"after": prev_date, "before": next_date, "days": j - i})
            i = j
        else:
            i += 1

    # Shop rows: column A from row 3 until a blank cell or a "Total" label.
    records = []
    anomalies = []
    for row_idx, row in enumerate(values[2:], start=2):
        shop = row[0].strip() if row else ""
        if not shop or shop.upper() == "TOTAL":
            break
        for b in date_blocks:
            s = b["start"]
            purchased = _int(row[s]) if s < len(row) else 0
            not_purchased = _int(row[s + 1]) if s + 1 < len(row) else 0
            for offset, field, value in ((0, "WALKINS PURCHASED", purchased), (1, "W.NOT PURCHASED", not_purchased)):
                if value < 0:
                    anomalies.append({
                        "shop": shop, "date": b["date"], "field": field,
                        "value": value, "cell": _cell_ref(row_idx, s + offset),
                    })
            records.append({
                "Shop": shop,
                "Date": b["date"],
                "Walkins Purchased": purchased,
                "Walkins Not Purchased": not_purchased,
                "Total": purchased + not_purchased,
            })

    df = pd.DataFrame(records, columns=["Shop", "Date", "Walkins Purchased", "Walkins Not Purchased", "Total"])
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
    return df, gaps, anomalies


def load_footfall_df(force_refresh: bool = False) -> pd.DataFrame:
    df, _, _ = _load(force_refresh)
    return df


def get_footfall_gaps(force_refresh: bool = False) -> list:
    _, gaps, _ = _load(force_refresh)
    return gaps


def get_footfall_anomalies(force_refresh: bool = False) -> list:
    _, _, anomalies = _load(force_refresh)
    return anomalies


def _load(force_refresh: bool):
    with _lock:
        if (
            not force_refresh
            and _cache["df"] is not None
            and time.time() - _cache["fetched_at"] < Config.SHEET_CACHE_TTL_SECONDS
        ):
            return _cache["df"], _cache["gaps"], _cache["anomalies"]

    values = get_worksheet_values(Config.SHEET_FOOTFALL, force_refresh=force_refresh)
    df, gaps, anomalies = _parse_footfall(values)

    with _lock:
        _cache["df"] = df
        _cache["gaps"] = gaps
        _cache["anomalies"] = anomalies
        _cache["fetched_at"] = time.time()

    return df, gaps, anomalies
