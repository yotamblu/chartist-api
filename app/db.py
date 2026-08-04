import asyncpg

from app.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def connect() -> None:
    global _pool
    # statement_cache_size=0 disables asyncpg's server-side prepared
    # statement cache. Without this, repeated identical queries against the
    # daily_prices hypertable get replanned as a generic plan after their
    # 5th execution (Postgres's default prepared-statement behavior) -- a
    # generic plan doesn't know the bind parameter values, so it can't
    # prune hypertable chunks by trade_date and ends up locking every
    # chunk, which is the "out of shared memory" failure mode this API is
    # supposed to avoid.
    _pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0
    )


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool
