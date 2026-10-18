"""Parser for the 'Revenue' sheet - a daily per-location revenue ledger kept
separately from the Shops sheet. Only the CORPORATE column is used here: the
other per-shop columns (NAIROBI, MOMBASA, ...) are already covered by the
Shops sheet's own transactions, but Corporate (bulk/B2B sales, handled by
named sales reps rather than shop staff - see the 'Corporate' sheet) isn't
recorded there at all, so this is the only source for it.

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
    if len(values) < 2:
        return pd.DataFrame(columns=["Date", "Corporate Revenue"])

    header = values[1]
    try:
        date_idx = next(i for i, h in enumerate(header) if h.strip().upper() == "DATE")
        corp_idx = next(i for i, h in enumerate(header) if h.strip().upper() == "CORPORATE")
    except StopIteration:
        return pd.DataFrame(columns=["Date", "Corporate Revenue"])

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
        records.append({"Date": date, "Corporate Revenue": corp_val})

    return pd.DataFrame(records, columns=["Date", "Corporate Revenue"])


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
