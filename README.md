# Chartist API

A FastAPI backend for Chartist, a stock analysis platform. It reads from and
writes to an existing Postgres/TimescaleDB database (symbols, exchanges,
daily prices, splits, dividends, and a profile cache) and enriches company
profile data live from Finnhub (stocks) and FMP (ETFs), caching the result
back into the database.

This service does **not** create or migrate any database schema — it
assumes the tables already exist and are populated.

## Project layout

```
main.py                  FastAPI app, CORS, router wiring
app/
  config.py               Env var loading (python-dotenv)
  db.py                   asyncpg connection pool
  models.py               Pydantic response models
  routers/
    symbols.py             /symbols/search, /symbols/{ticker}/profile, /symbols/{ticker}/prices
    exchanges.py            /exchanges
  providers/
    finnhub.py              Finnhub stock profile client
    fmp.py                   FMP ETF/company profile client
```

## Endpoints

- `GET /symbols/search?q=&exchange=&type=&limit=` — search symbols by ticker/name.
- `GET /symbols/{ticker}/profile` — write-through cached company profile, routed
  to Finnhub for stocks and FMP for ETFs, falling back to the cache if the live
  call fails.
- `GET /symbols/{ticker}/prices?from=&to=&limit=` — daily OHLCV bars with both
  raw and split-adjusted prices. Defaults to the last 2 years.
- `GET /exchanges` — list of exchanges.

## Setup

### 1. Prerequisites

- Python 3.11+
- Access to an existing Postgres/TimescaleDB instance with the Chartist schema
  already populated.
- API keys for [Finnhub](https://finnhub.io) and
  [Financial Modeling Prep](https://site.financialmodelingprep.com/).

### 2. Environment variables

Copy the example env file and fill in your own values:

```bash
cp .env.example .env
```

`.env` requires:

| Variable          | Description                                   |
| ----------------- | ---------------------------------------------- |
| `DATABASE_URL`    | Postgres connection string, e.g. `postgresql://user:password@localhost:5432/chartist` |
| `FINNHUB_API_KEY` | API key for Finnhub (used for stock profiles) |
| `FMP_API_KEY`     | API key for Financial Modeling Prep (used for ETF profiles) |

### 3. Install dependencies

It's recommended to use a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS/Linux

pip install -r requirements.txt
```

### 4. Run locally

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`.

## Notes

- `daily_prices` is a TimescaleDB hypertable partitioned on `trade_date`.
  Every query against it includes a `trade_date` filter (and a `LIMIT`) to
  avoid locking every chunk.
- Split adjustment is computed at read time from the `splits` table — stored
  price data is never rewritten.
- If a live provider call fails (network error, rate limit, etc.), the
  `/symbols/{ticker}/profile` endpoint falls back to whatever is already in
  `symbol_profile_cache` instead of erroring out. If neither the live call
  nor the cache has data, it returns `502`.
