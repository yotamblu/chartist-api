# Chartist API

A FastAPI backend for Chartist, a stock analysis platform. It reads from and
writes to an existing Postgres/TimescaleDB database (symbols, exchanges,
daily prices, splits, dividends, and a profile cache) and enriches company
profile data live from Financial Modeling Prep (FMP), for both stocks and
ETFs, caching the result back into the database.

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
    fmp.py                   FMP company/fund profile client
```

## Endpoints

- `GET /symbols/search?q=&exchange=&type=&limit=` — search symbols by ticker/name.
- `GET /symbols/{ticker}/profile` — write-through cached company profile, fetched
  live from FMP for both stocks and ETFs, falling back to the cache if the live
  call fails.
- `GET /symbols/{ticker}/prices?from=&to=&limit=` — daily OHLCV bars with both
  raw and split-adjusted prices. Omitting `from` returns the symbol's full
  available history (not just a fixed lookback window).
- `GET /symbols/{ticker}/dividends?years=20` — every dividend paid in the
  last `years` years (default 20), each with the closing price on/just
  before its ex-date and the yield that dividend represented at the time
  (`amount / price_at_ex_date * 100`). Also returns the trailing-12-month
  dividend total and the stock's current dividend yield
  (`trailing_12m_dividend_amount / current_price * 100`) — future,
  not-yet-paid ex-dates that happen to already be in the `dividends` table
  are excluded from the trailing-12-month figure.
- `GET /exchanges` — list of exchanges.

## Setup

### 1. Prerequisites

- Python 3.11+
- Access to an existing Postgres/TimescaleDB instance with the Chartist schema
  already populated.
- An API key for [Financial Modeling Prep](https://site.financialmodelingprep.com/).

### 2. Environment variables

Copy the example env file and fill in your own values:

```bash
cp .env.example .env
```

`.env` requires:

| Variable          | Description                                   |
| ----------------- | ---------------------------------------------- |
| `DATABASE_URL`    | Postgres connection string, e.g. `postgresql://user:password@localhost:5432/chartist` |
| `FMP_KEY`         | API key for Financial Modeling Prep (used for stock and ETF profiles) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins. Defaults to `http://localhost:3000` if unset. |

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

## Deploying to Railway

This repo is ready to deploy on [Railway](https://railway.app/) as-is:

1. Create a new Railway project from this GitHub repo (or `railway init` +
   `railway up` from a local checkout).
2. In the service's **Variables** tab, set `DATABASE_URL`, `FMP_KEY`, and
   `ALLOWED_ORIGINS` (your deployed frontend's origin, e.g.
   `https://your-frontend.example.com`) — same variables as `.env.example`.
   Railway does not read `.env` files from the repo; it injects these as
   real environment variables.
3. Railway auto-detects this as a Python app (Nixpacks, using
   `requirements.txt` and `.python-version`) and uses the start command
   from `railway.json` / `Procfile`:
   `uvicorn main:app --host 0.0.0.0 --port $PORT`. `$PORT` is provided by
   Railway at runtime — don't hardcode a port.
4. Railway will health-check `GET /health` (configured in `railway.json`)
   to confirm the deploy is live.
5. Generate a public domain for the service from the Railway dashboard
   (Settings → Networking) to get a URL your frontend can call.

No database migration step is needed or wanted — this service only reads
from and writes to tables that already exist in the target Postgres
instance.

## Notes

- `daily_prices` is a TimescaleDB hypertable with ~1,400 chunks across its
  full history. Every query against it includes a `trade_date` filter (and
  a `LIMIT`) to avoid locking every chunk. A single query spanning a very
  wide range (tens of years) can still lock more chunks than Postgres's
  `max_locks_per_transaction` allows, so `/symbols/{ticker}/prices` fetches
  wide ranges (including the full-history default) in fixed 5-year windows
  and concatenates the results rather than issuing one unbounded query.
- Split adjustment is computed at read time from the `splits` table — stored
  price data is never rewritten.
- If a live provider call fails (network error, rate limit, etc.), the
  `/symbols/{ticker}/profile` endpoint falls back to whatever is already in
  `symbol_profile_cache` instead of erroring out. If neither the live call
  nor the cache has data, it returns `502`.
