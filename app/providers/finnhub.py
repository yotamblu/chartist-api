"""Finnhub provider - used for 'stock' security_type profiles."""

import httpx

from app.config import FINNHUB_API_KEY

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


async def fetch_stock_profile(ticker: str) -> dict:
    """Fetch a company profile from Finnhub's /stock/profile2 endpoint.

    Returns a dict normalized to the symbol_profile_cache column shape.
    Raises httpx.HTTPError (or subclasses) on any network/HTTP failure so
    callers can fall back to cached data.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{FINNHUB_BASE_URL}/stock/profile2",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
        )
        response.raise_for_status()
        data = response.json()

    if not data:
        raise httpx.HTTPError(f"Finnhub returned no profile data for {ticker}")

    return {
        "market_cap": data.get("marketCapitalization"),
        "logo_url": data.get("logo"),
        "description": None,
        "sector": None,
        "industry": data.get("finnhubIndustry"),
        "website": data.get("weburl"),
        "employees": None,
        "pe_ratio": None,
        "week52_high": None,
        "week52_low": None,
        "source": "finnhub",
    }
