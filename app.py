from fastapi import FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
import time
from collections import defaultdict

app = FastAPI(title="Orders API")

# CORS Fix
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,      # Important fix
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stores
orders_db: Dict[str, dict] = {}
order_list: List[dict] = [
    {"id": i, "name": f"Order {i}", "amount": 10.0 * i} for i in range(1, 57)
]

rate_limits: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT = 17
WINDOW = 10

idempotency_store: Dict[str, dict] = {}

class OrderResponse(BaseModel):
    id: int
    name: str
    amount: float
    created_at: Optional[float] = None

# Global Rate Limiting Middleware (Most Reliable)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id", "default")
    now = time.time()
    timestamps = rate_limits[client_id]

    # Remove old timestamps
    while timestamps and now - timestamps[0] >= WINDOW:
        timestamps.pop(0)

    if len(timestamps) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW - (now - timestamps[0])) + 1)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)}
        )

    timestamps.append(now)
    return await call_next(request)


@app.post("/orders", status_code=201)
async def create_order(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]
    
    order_id = len(orders_db) + 1
    order = {
        "id": order_id,
        "name": f"Order {order_id}",
        "amount": 10.0 * order_id,
        "created_at": time.time()
    }
    orders_db[idempotency_key] = order
    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
async def get_orders(
    limit: int = Query(10, ge=1, le=50),
    cursor: Optional[str] = Query(None)
):
    start_idx = int(cursor) if cursor and cursor.isdigit() else 0
    if not (0 <= start_idx < len(order_list)):
        start_idx = 0
    
    end_idx = min(start_idx + limit, len(order_list))
    items = order_list[start_idx:end_idx]
    next_cursor = str(end_idx) if end_idx < len(order_list) else None
    
    return {"items": items, "next_cursor": next_cursor}


@app.get("/orders/{order_id}")
async def get_order(order_id: int):
    if not (1 <= order_id <= 56):
        raise HTTPException(404, "Order not found")
    return order_list[order_id - 1]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
