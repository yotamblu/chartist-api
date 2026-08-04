from datetime import date, datetime

from pydantic import BaseModel


class ExchangeOut(BaseModel):
    exchange_id: int
    code: str
    name: str


class SymbolSearchResult(BaseModel):
    symbol_id: int
    ticker: str
    name: str | None
    exchange_code: str | None
    security_type: str


class SymbolProfile(BaseModel):
    symbol_id: int
    ticker: str
    market_cap: float | None = None
    logo_url: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    employees: int | None = None
    pe_ratio: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    source: str | None = None
    fetched_at: datetime | None = None


class PriceBar(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int | None
    adjustment_factor: float
    adjusted_open: float
    adjusted_high: float
    adjusted_low: float
    adjusted_close: float


class PriceSeries(BaseModel):
    symbol_id: int
    ticker: str
    bars: list[PriceBar]


class DividendEntry(BaseModel):
    ex_date: date
    amount: float
    price_at_ex_date: float | None = None
    yield_at_ex_date: float | None = None  # percent, amount / price_at_ex_date * 100


class DividendHistory(BaseModel):
    symbol_id: int
    ticker: str
    dividends: list[DividendEntry]
    trailing_12m_dividend_amount: float
    current_price: float | None = None
    current_dividend_yield: float | None = None  # percent, TTM dividends / current_price
