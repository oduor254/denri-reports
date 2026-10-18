"""Parser for the 'Corporate' sheet - the corporate client roster. This is a
lifetime cumulative list (each row's First/Last Order are that client's own
order history), not a per-transaction log with a date per row, so unlike the
Shops sheet it can't be filtered into day/week/month windows - it's reported
as an all-time ranking instead (see app/metrics/corporate.py).
"""
import threading
import time

import pandas as pd

from app.config import Config
from app.sheets_client import get_worksheet_values

COLUMNS = ["Customer", "Type", "Phone", "Orders", "Bags", "Revenue", "First Order", "Last Order", "Where", "Served By"]

_lock = threading.Lock()
_cache = {"fetched_at": 0.0, "df": None}


def _money(v: str) -> float:
    v = v.strip().replace(",", "")
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _int(v: str) -> int:
    v = v.strip().replace(",", "")
    try:
        return int(float(v)) if v else 0
    except ValueError:
        return 0


def _parse_corporate(values: list) -> pd.DataFrame:
    records = []
    for row in values[1:]:
        padded = (row + [""] * len(COLUMNS))[: len(COLUMNS)]
        customer = padded[0].strip()
        if not customer or customer.upper().startswith("TOTAL"):
            continue
        records.append({
            "Customer": customer,
            "Phone": padded[2].strip(),
            "Orders": _int(padded[3]),
            "Bags": _int(padded[4]),
            "Revenue": _money(padded[5]),
            "First Order": padded[6].strip(),
            "Last Order": padded[7].strip(),
            "Served By": padded[9].strip(),
        })

    return pd.DataFrame(
        records,
        columns=["Customer", "Phone", "Orders", "Bags", "Revenue", "First Order", "Last Order", "Served By"],
    )


def load_corporate_df(force_refresh: bool = False) -> pd.DataFrame:
    with _lock:
        if (
            not force_refresh
            and _cache["df"] is not None
            and time.time() - _cache["fetched_at"] < Config.SHEET_CACHE_TTL_SECONDS
        ):
            return _cache["df"]

    values = get_worksheet_values(Config.SHEET_CORPORATE, force_refresh=force_refresh)
    df = _parse_corporate(values)

    with _lock:
        _cache["df"] = df
        _cache["fetched_at"] = time.time()

    return df
