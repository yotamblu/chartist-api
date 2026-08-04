"""FMP (Financial Modeling Prep) provider - used for all symbol profiles
(stocks and ETFs alike).

Uses FMP's general company profile endpoint. This is not fund-specific, so
expense ratio / holdings data for ETFs is not available and is left null.
pe_ratio is also not present in this endpoint's response and is left null.
"""

import httpx

from app.config import FMP_API_KEY

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


async def fetch_profile(ticker: str) -> dict:
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

    employees = None
    raw_employees = profile.get("fullTimeEmployees")
    if raw_employees not in (None, ""):
        try:
            employees = int(raw_employees)
        except (TypeError, ValueError):
            employees = None

    week52_low, week52_high = None, None
    week52_range = profile.get("range")
    if week52_range and "-" in week52_range:
        low_str, high_str = week52_range.split("-", 1)
        try:
            week52_low = float(low_str)
            week52_high = float(high_str)
        except ValueError:
            week52_low, week52_high = None, None

    return {
        "market_cap": profile.get("marketCap"),
        "logo_url": profile.get("image"),
        "description": profile.get("description"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "website": profile.get("website"),
        "employees": employees,
        "pe_ratio": None,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "source": "fmp",
    }
