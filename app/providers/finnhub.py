"""Finnhub provider - used for 'stock' security_type profiles."""

import httpx

from app.config import FINNHUB_API_KEY

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


async def fetch_stock_profile(ticker: str) -> dict:
    """Fetch a company profile from Finnhub's /stock/profile2 endpoint,
    supplemented with PE ratio and 52-week high/low from /stock/metric.

    Returns a dict normalized to the symbol_profile_cache column shape.
    Raises httpx.HTTPError (or subclasses) on any network/HTTP failure of
    the profile2 call so callers can fall back to cached data. `description`
    and `employees` are always null here -- Finnhub's free tier does not
    expose either field for stock profiles.
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

        pe_ratio = None
        week52_high = None
        week52_low = None
        try:
            metric_response = await client.get(
                f"{FINNHUB_BASE_URL}/stock/metric",
                params={"symbol": ticker, "metric": "all", "token": FINNHUB_API_KEY},
            )
            metric_response.raise_for_status()
            metric = metric_response.json().get("metric") or {}
            pe_ratio = metric.get("peTTM") or metric.get("peNormalizedAnnual")
            week52_high = metric.get("52WeekHigh")
            week52_low = metric.get("52WeekLow")
        except httpx.HTTPError:
            pass

    return {
        "market_cap": data.get("marketCapitalization"),
        "logo_url": data.get("logo"),
        "description": None,
        "sector": None,
        "industry": data.get("finnhubIndustry"),
        "website": data.get("weburl"),
        "employees": None,
        "pe_ratio": pe_ratio,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "source": "finnhub",
    }
