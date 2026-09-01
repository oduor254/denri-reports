import threading
import time

import pandas as pd

from app.config import Config
from app.sheets_client import get_worksheet_values

COLUMNS = [
    "Date", "First Name", "Gender", "Phone", "Product", "Color", "Category",
    "Location", "Price", "Quantity", "Total", "Customer Type", "Comparison",
    "mmm", "Repeat",
]

_lock = threading.Lock()
_cache = {"fetched_at": 0.0, "df": None}


def _classify_phone_kyc(phone: str) -> str:
    """Strict KYC classification, distinct from the looser 'Phone Valid' column
    (which only needs to be good enough for customer dedup elsewhere).

    - 'na': blank, or the literal text 'N/A' some rows already have in this field.
    - 'valid': the standard East African mobile format - 9 digits starting 7/1/6
      (leading 0 dropped, e.g. 702447155), OR 10 digits starting with a literal
      leading 0 (e.g. 0702447155), OR 11-15 digits (a plausible international
      number with country code - the data has real examples: 1... US/Canada,
      256... Uganda, 44... UK, 234... Nigeria).
    - 'invalid': everything else - notably 9-digit numbers not starting 7/1/6
      (don't match any KE mobile prefix), 6-8 digit numbers (too short - look
      like truncated/mistyped entries), and 10-digit numbers not starting with
      0 (look like a KE number with a stray extra digit, not a real 10-digit
      number).
    """
    p = phone.strip()
    if p == "" or p.upper() == "N/A":
        return "na"
    if not p.isdigit():
        return "invalid"
    n = len(p)
    if n == 9 and p[0] in "716":
        return "valid"
    if n == 10 and p[0] == "0":
        return "valid"
    if 11 <= n <= 15:
        return "valid"
    return "invalid"


def _parse_shops(values):
    rows = values[1:]
    trimmed = [
        (r + [""] * len(COLUMNS))[: len(COLUMNS)] for r in rows
    ]
    df = pd.DataFrame(trimmed, columns=COLUMNS)
    df = df[df["Date"].str.strip() != ""]

    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df = df.dropna(subset=["Date"])

    for col in ("Price", "Quantity", "Total"):
        df[col] = (
            df[col].str.replace(",", "", regex=False).replace("", "0").astype(float)
        )

    df["Phone"] = df["Phone"].str.strip()
    df["Phone Valid"] = df["Phone"].str.match(r"^\d{9}$|^\d{10}$|^\d{12}$")
    df["Phone KYC"] = df["Phone"].apply(_classify_phone_kyc)

    df["Repeat"] = df["Repeat"].str.strip().str.lower() == "yes"
    # Comparison == TRUE flags a transaction where the phone captured is the
    # shop's own contact number rather than the customer's (a KYC red flag).
    df["Comparison"] = df["Comparison"].str.strip().str.upper() == "TRUE"
    df["Customer Type"] = df["Customer Type"].str.strip().str.lower()
    df["Location"] = df["Location"].str.strip().replace({"Ktda": "KTDA"})
    # Gender has case-dupes ("male"/"female" vs "Male"/"Female") plus real "N/A"
    # values already in the sheet - .title() folds the dupes without disturbing
    # N/A. The sheet also has two labels for the same non-individual-customer
    # category ("Organization" on older rows, "Corporate" on newer ones, since
    # whoever enters data switched terms) - fold the older label into the
    # current one so they aren't shown as two separate categories.
    df["Gender"] = df["Gender"].str.strip().str.title().replace({"Organization": "Corporate"})

    return df.reset_index(drop=True)


def load_shops_df(force_refresh: bool = False) -> pd.DataFrame:
    with _lock:
        if (
            not force_refresh
            and _cache["df"] is not None
            and time.time() - _cache["fetched_at"] < Config.SHEET_CACHE_TTL_SECONDS
        ):
            return _cache["df"]

    values = get_worksheet_values(Config.SHEET_SHOPS, force_refresh=force_refresh)
    df = _parse_shops(values)

    with _lock:
        _cache["df"] = df
        _cache["fetched_at"] = time.time()

    return df
