import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
FINNHUB_API_KEY = os.environ.get("FINNHUB_KEY", "")
FMP_API_KEY = os.environ.get("FMP_KEY", "")
