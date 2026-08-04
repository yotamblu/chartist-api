from bisect import bisect_right
from datetime import date, timedelta

import asyncpg
from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from app.models import (
    DividendEntry,
    DividendHistory,
    PriceBar,
    PriceSeries,
    SymbolProfile,
    SymbolSearchResult,
)
from app.providers.fmp import fetch_profile

router = APIRouter(prefix="/symbols", tags=["symbols"])

# daily_prices is a TimescaleDB hypertable chunked by trade_date. A single
# query spanning a wide date range has to lock every chunk it overlaps, and
# this table has ~1,400 chunks across its full ~25-year history -- more
# than Postgres's max_locks_per_transaction allows in one query (confirmed:
# a ~24-year span reliably throws OutOfMemoryError / "out of shared
# memory", a ~23-year span doesn't). Fetching in fixed-size windows well
# under that ceiling keeps every individual query safe regardless of how
# wide the overall requested range is.
_SAFE_WINDOW_DAYS = 365 * 5


async def _fetch_price_rows_windowed(
    pool: asyncpg.Pool,
    symbol_id: int,
    from_date: date,
    to_date: date,
    limit: int,
) -> list[asyncpg.Record]:
    rows: list[asyncpg.Record] = []
    window_start = from_date
    while window_start <= to_date and len(rows) < limit:
        window_end = min(window_start + timedelta(days=_SAFE_WINDOW_DAYS), to_date)
        window_rows = await pool.fetch(
            """
            SELECT trade_date, open, high, low, close, volume
            FROM daily_prices
            WHERE symbol_id = $1 AND trade_date BETWEEN $2 AND $3
            ORDER BY trade_date ASC
            LIMIT $4
            """,
            symbol_id,
            window_start,
            window_end,
            limit - len(rows),
        )
        rows.extend(window_rows)
        window_start = window_end + timedelta(days=1)
    return rows


async def _earliest_available_trade_date(pool: asyncpg.Pool) -> date | None:
    # Reads TimescaleDB's chunk catalog (metadata only, not the hypertable
    # itself) so this never risks the same chunk-locking problem.
    return await pool.fetchval(
        """
        SELECT min(range_start)::date
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'daily_prices'
        """
    )


async def _get_symbol_by_ticker(pool: asyncpg.Pool, ticker: str) -> asyncpg.Record:
    row = await pool.fetchrow(
        """
        SELECT symbol_id, ticker, security_type
        FROM symbols
        WHERE ticker = $1
        """,
        ticker.upper(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{ticker}' not found")
    return row


@router.get("/search", response_model=list[SymbolSearchResult])
async def search_symbols(
    q: str = Query(..., min_length=1),
    exchange: str | None = Query(None),
    type: str | None = Query(None, pattern="^(stock|etf)$"),
    limit: int = Query(20, ge=1, le=100),
):
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT s.symbol_id, s.ticker, s.name, e.code AS exchange_code, s.security_type
        FROM symbols s
        LEFT JOIN exchanges e ON e.exchange_id = s.exchange_id
        WHERE (s.ticker ILIKE $1 OR s.name ILIKE $1)
          AND ($2::text IS NULL OR e.code = $2)
          AND ($3::text IS NULL OR s.security_type::text = $3)
        ORDER BY
          CASE
            WHEN s.ticker ILIKE $4 THEN 0
            WHEN s.ticker ILIKE $5 THEN 1
            ELSE 2
          END,
          s.ticker
        LIMIT $6
        """,
        f"%{q}%",
        exchange,
        type,
        q,
        f"{q}%",
        limit,
    )
    return [SymbolSearchResult(**dict(row)) for row in rows]


@router.get("/{ticker}/profile", response_model=SymbolProfile)
async def get_symbol_profile(ticker: str):
    pool = get_pool()
    symbol = await _get_symbol_by_ticker(pool, ticker)
    symbol_id = symbol["symbol_id"]

    try:
        live_data = await fetch_profile(symbol["ticker"])
    except Exception:
        live_data = None

    if live_data is not None:
        row = await pool.fetchrow(
            """
            INSERT INTO symbol_profile_cache (
                symbol_id, market_cap, logo_url, description, sector,
                industry, website, employees, pe_ratio, week52_high,
                week52_low, source, fetched_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now())
            ON CONFLICT (symbol_id) DO UPDATE SET
                market_cap = EXCLUDED.market_cap,
                logo_url = EXCLUDED.logo_url,
                description = EXCLUDED.description,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                website = EXCLUDED.website,
                employees = EXCLUDED.employees,
                pe_ratio = EXCLUDED.pe_ratio,
                week52_high = EXCLUDED.week52_high,
                week52_low = EXCLUDED.week52_low,
                source = EXCLUDED.source,
                fetched_at = EXCLUDED.fetched_at
            RETURNING market_cap, logo_url, description, sector, industry,
                      website, employees, pe_ratio, week52_high, week52_low,
                      source, fetched_at
            """,
            symbol_id,
            live_data["market_cap"],
            live_data["logo_url"],
            live_data["description"],
            live_data["sector"],
            live_data["industry"],
            live_data["website"],
            live_data["employees"],
            live_data["pe_ratio"],
            live_data["week52_high"],
            live_data["week52_low"],
            live_data["source"],
        )
        if row is not None:
            return SymbolProfile(
                symbol_id=symbol_id, ticker=symbol["ticker"], **dict(row)
            )
        return SymbolProfile(symbol_id=symbol_id, ticker=symbol["ticker"], **live_data)

    cached = await pool.fetchrow(
        """
        SELECT market_cap, logo_url, description, sector, industry, website,
               employees, pe_ratio, week52_high, week52_low, source, fetched_at
        FROM symbol_profile_cache
        WHERE symbol_id = $1
        """,
        symbol_id,
    )
    if cached is None:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch live profile for '{ticker}' and no cached data is available",
        )
    return SymbolProfile(symbol_id=symbol_id, ticker=symbol["ticker"], **dict(cached))


@router.get("/{ticker}/prices", response_model=PriceSeries)
async def get_symbol_prices(
    ticker: str,
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    limit: int = Query(20000, ge=1, le=50000),
):
    pool = get_pool()
    symbol = await _get_symbol_by_ticker(pool, ticker)
    symbol_id = symbol["symbol_id"]

    to_date = to or date.today()
    if from_ is not None:
        from_date = from_
    else:
        # No lower bound given -> return the symbol's full available
        # history, not just a fixed lookback window.
        from_date = await _earliest_available_trade_date(pool) or (
            to_date - timedelta(days=365 * 2)
        )

    price_rows = await _fetch_price_rows_windowed(
        pool, symbol_id, from_date, to_date, limit
    )

    split_rows = await pool.fetch(
        """
        SELECT ex_date, ratio
        FROM splits
        WHERE symbol_id = $1
        ORDER BY ex_date ASC
        """,
        symbol_id,
    )
    splits = [(row["ex_date"], float(row["ratio"])) for row in split_rows]

    bars = []
    for row in price_rows:
        trade_date = row["trade_date"]
        factor = 1.0
        for ex_date, ratio in splits:
            if ex_date > trade_date:
                factor *= ratio

        open_, high, low, close = (
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
        )
        bars.append(
            PriceBar(
                trade_date=trade_date,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=row["volume"],
                adjustment_factor=factor,
                adjusted_open=open_ / factor,
                adjusted_high=high / factor,
                adjusted_low=low / factor,
                adjusted_close=close / factor,
            )
        )

    return PriceSeries(symbol_id=symbol_id, ticker=symbol["ticker"], bars=bars)


@router.get("/{ticker}/dividends", response_model=DividendHistory)
async def get_symbol_dividends(ticker: str, years: int = Query(20, ge=1, le=50)):
    pool = get_pool()
    symbol = await _get_symbol_by_ticker(pool, ticker)
    symbol_id = symbol["symbol_id"]

    cutoff = date.today() - timedelta(days=365 * years)
    dividend_rows = await pool.fetch(
        """
        SELECT ex_date, amount
        FROM dividends
        WHERE symbol_id = $1 AND ex_date >= $2
        ORDER BY ex_date ASC
        """,
        symbol_id,
        cutoff,
    )

    if not dividend_rows:
        return DividendHistory(
            symbol_id=symbol_id,
            ticker=symbol["ticker"],
            dividends=[],
            trailing_12m_dividend_amount=0.0,
            current_price=None,
            current_dividend_yield=None,
        )

    earliest_ex_date = dividend_rows[0]["ex_date"]

    # Close prices to look up the price on/around each ex_date, plus the
    # most recent close for the current yield. Uses the same safe windowed
    # fetch as /prices to avoid locking too many hypertable chunks in one
    # go over a potentially decades-wide range.
    price_rows = await _fetch_price_rows_windowed(
        pool,
        symbol_id,
        earliest_ex_date - timedelta(days=14),
        date.today(),
        50000,
    )
    prices_by_date = {row["trade_date"]: float(row["close"]) for row in price_rows}
    sorted_trade_dates = sorted(prices_by_date)

    def price_on_or_before(target: date) -> float | None:
        idx = bisect_right(sorted_trade_dates, target) - 1
        if idx < 0:
            return None
        return prices_by_date[sorted_trade_dates[idx]]

    dividends = []
    for row in dividend_rows:
        ex_date = row["ex_date"]
        amount = float(row["amount"])
        price = price_on_or_before(ex_date)
        dividends.append(
            DividendEntry(
                ex_date=ex_date,
                amount=amount,
                price_at_ex_date=price,
                yield_at_ex_date=(amount / price * 100) if price else None,
            )
        )

    today = date.today()
    ttm_cutoff = today - timedelta(days=365)
    trailing_12m_amount = sum(
        float(row["amount"])
        for row in dividend_rows
        if ttm_cutoff <= row["ex_date"] <= today
    )

    current_price = prices_by_date[sorted_trade_dates[-1]] if sorted_trade_dates else None
    current_dividend_yield = (
        (trailing_12m_amount / current_price * 100) if current_price else None
    )

    return DividendHistory(
        symbol_id=symbol_id,
        ticker=symbol["ticker"],
        dividends=dividends,
        trailing_12m_dividend_amount=round(trailing_12m_amount, 6),
        current_price=current_price,
        current_dividend_yield=(
            round(current_dividend_yield, 4)
            if current_dividend_yield is not None
            else None
        ),
    )
