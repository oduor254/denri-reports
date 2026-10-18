"""Parser for the 'Revenue' sheet - a daily per-location revenue ledger kept
separately from the Shops sheet. This is the hand-reconciled source of truth
for the report's headline Revenue figures (daily/weekly/monthly): the
per-shop transaction log (Shops sheet) and this ledger drift apart by small
amounts over time as entries get corrected at source, so "Revenue" is
reported from here, not re-summed from raw transactions. The CORPORATE
column (bulk/B2B sales, handled by named sales reps - see the 'Corporate'
sheet) isn't recorded in the Shops sheet at all, so this is also the only
source for it.

Structure: row 0 is blank, row 1 holds headers ('DATE', shop names, ...,
'CORPORATE', ...), data runs from row 2 until a 'TOTAL' row in the DATE
column (the sheet's own running total, recomputed here instead of trusted
as text).
"""
import threading
import time

import pandas as pd

from app.config import Config
from app.sheets_client import get_worksheet_values

_lock = threading.Lock()
_cache = {"fetched_at": 0.0, "df": None}


def _money(v: str) -> float:
    v = v.strip().replace(",", "")
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _parse_revenue(values: list) -> pd.DataFrame:
    columns = ["Date", "Retail Revenue", "Corporate Revenue"]
    if len(values) < 2:
        return pd.DataFrame(columns=columns)

    header = values[1]
    try:
        date_idx = next(i for i, h in enumerate(header) if h.strip().upper() == "DATE")
        corp_idx = next(i for i, h in enumerate(header) if h.strip().upper() == "CORPORATE")
    except StopIteration:
        return pd.DataFrame(columns=columns)

    # Retail Revenue = every per-location column (NAIROBI, MOMBASA, ..., WEBSITE,
    # JUMIA, ...) - explicitly excluding DATE, CORPORATE (a distinct sales
    # channel, reported separately) and any sheet-computed rollup column
    # (e.g. a 'TOTAL' column the sheet already sums its own rows into) -
    # summing a rollup alongside the columns it rolls up would double-count.
    _EXCLUDE = {"DATE", "CORPORATE", "TOTAL", "SUM", "GRAND TOTAL"}
    retail_idxs = [
        i for i in range(len(header))
        if header[i].strip() and header[i].strip().upper() not in _EXCLUDE
    ]

    records = []
    for row in values[2:]:
        if date_idx >= len(row):
            continue
        date_str = row[date_idx].strip()
        if not date_str or date_str.upper() == "TOTAL":
            continue
        date = pd.to_datetime(date_str, format="%m/%d/%Y", errors="coerce")
        if pd.isna(date):
            continue
        corp_val = _money(row[corp_idx]) if corp_idx < len(row) else 0.0
        retail_val = sum(_money(row[i]) for i in retail_idxs if i < len(row))
        records.append({"Date": date, "Retail Revenue": retail_val, "Corporate Revenue": corp_val})

    return pd.DataFrame(records, columns=columns)


def load_revenue_sheet_df(force_refresh: bool = False) -> pd.DataFrame:
    with _lock:
        if (
            not force_refresh
            and _cache["df"] is not None
            and time.time() - _cache["fetched_at"] < Config.SHEET_CACHE_TTL_SECONDS
        ):
            return _cache["df"]

    values = get_worksheet_values(Config.SHEET_REVENUE, force_refresh=force_refresh)
    df = _parse_revenue(values)

    with _lock:
        _cache["df"] = df
        _cache["fetched_at"] = time.time()

    return df
