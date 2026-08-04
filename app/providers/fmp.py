"""FMP (Financial Modeling Prep) provider - used for 'etf' security_type profiles.

Uses FMP's general company profile endpoint. This is not fund-specific, so
expense ratio / holdings data is not available and is left null.
"""

import httpx

from app.config import FMP_API_KEY

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


async def fetch_etf_profile(ticker: str) -> dict:
    """Fetch a company/fund profile from FMP's /stable/profile endpoint.

    Returns a dict normalized to the symbol_profile_cache column shape.
    Raises httpx.HTTPError (or subclasses) on any network/HTTP failure so
    callers can fall back to cached data.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{FMP_BASE_URL}/profile",
            params={"symbol": ticker, "apikey": FMP_API_KEY},
        )
        response.raise_for_status()
        data = response.json()

    if not data:
        raise httpx.HTTPError(f"FMP returned no profile data for {ticker}")

    profile = data[0] if isinstance(data, list) else data

    return {
        "market_cap": profile.get("marketCap"),
        "logo_url": profile.get("image"),
        "description": profile.get("description"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "website": profile.get("website"),
        "employees": None,
        "pe_ratio": None,
        "week52_high": None,
        "week52_low": None,
        "source": "fmp",
    }
