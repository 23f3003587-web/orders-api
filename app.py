from fastapi import FastAPI, Header, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict
from typing import Optional
import time

app = FastAPI(title="Orders API")

# Fixed CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fixed catalog (1..56)
order_list = [
    {"id": i, "name": f"Order {i}", "amount": 10.0 * i} for i in range(1, 57)
]

idempotency_store: dict = {}
rate_limits: dict = defaultdict(list)
RATE_LIMIT = 17
WINDOW = 10

# Rate limit middleware (skips OPTIONS)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    client_id = request.headers.get("X-Client-Id", "default")
    now = time.time()
    timestamps = rate_limits[client_id]
    while timestamps and now - timestamps[0] >= WINDOW:
        timestamps.pop(0)
    if len(timestamps) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW - (now - timestamps[0])) + 1) if timestamps else WINDOW
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)}
        )
    timestamps.append(now)
    return await call_next(request)


@app.post("/orders", status_code=201)
async def create_order(idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]
    # Safe unique ID
    order_id = 1000 + len(idempotency_store) + 1
    order = {
        "id": order_id,
        "name": f"Order {order_id}",
        "amount": 10.0 * order_id,
        "created_at": time.time()
    }
    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
async def get_orders(
    limit: int = Query(10, ge=1, le=100),
    cursor: Optional[str] = Query(None)
):
    try:
        start_idx = int(cursor) if cursor and cursor.isdigit() else 0
    except (ValueError, TypeError):
        start_idx = 0
    if start_idx < 0 or start_idx >= len(order_list):
        start_idx = 0
    end_idx = min(start_idx + limit, len(order_list))
    items = order_list[start_idx:end_idx]
    next_cursor = str(end_idx) if end_idx < len(order_list) else None
    return {"items": items, "next_cursor": next_cursor}


@app.get("/")
async def root():
    return {"status": "ok", "total_orders": len(order_list)}
