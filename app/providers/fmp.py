"""FMP (Financial Modeling Prep) provider - used for all symbol profiles
(stocks and ETFs alike).

Combines FMP's general company profile endpoint with its TTM ratios
endpoint (for pe_ratio, which the profile endpoint does not return). The
profile endpoint is not fund-specific, so expense ratio / holdings data for
ETFs is not available and is left null. The ratios endpoint returns no data
for ETFs, so pe_ratio is left null for them too.
"""

import httpx

from app.config import FMP_API_KEY

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


async def _fetch_pe_ratio(client: httpx.AsyncClient, ticker: str) -> float | None:
    try:
        response = await client.get(
            f"{FMP_BASE_URL}/ratios-ttm",
            params={"symbol": ticker, "apikey": FMP_API_KEY},
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not data:
        return None

    ratios = data[0] if isinstance(data, list) else data
    return ratios.get("priceToEarningsRatioTTM")


async def fetch_profile(ticker: str) -> dict:
    """Fetch a company/fund profile from FMP's /stable/profile endpoint,
    supplemented with pe_ratio from /stable/ratios-ttm.

    Returns a dict normalized to the symbol_profile_cache column shape.
    Raises httpx.HTTPError (or subclasses) on any network/HTTP failure of
    the profile call so callers can fall back to cached data. A failure of
    the supplementary ratios call only leaves pe_ratio null.
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

        pe_ratio = await _fetch_pe_ratio(client, ticker)

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
        "pe_ratio": pe_ratio,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "source": "fmp",
    }
