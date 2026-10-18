import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
    GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE")
    PORT = int(os.environ.get("PORT", 5050))
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    SHEET_SHOPS = "Shops"
    SHEET_FEEDBACK = "Revamped feedback"
    SHEET_FOOTFALL = "Footfall"
    SHEET_REVENUE = "Revenue"
    SHEET_CORPORATE = "Corporate"

    SHEET_CACHE_TTL_SECONDS = 300
