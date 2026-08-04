from fastapi import APIRouter

from app.db import get_pool
from app.models import ExchangeOut

router = APIRouter(prefix="/exchanges", tags=["exchanges"])


@router.get("", response_model=list[ExchangeOut])
async def list_exchanges():
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT exchange_id, code, name FROM exchanges ORDER BY code"
    )
    return [ExchangeOut(**dict(row)) for row in rows]
