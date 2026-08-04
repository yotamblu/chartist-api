import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
FMP_API_KEY = os.environ.get("FMP_KEY", "")

# Comma-separated list of allowed CORS origins, e.g.
# "http://localhost:3000,https://chartist.example.com"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
