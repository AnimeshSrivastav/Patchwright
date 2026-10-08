from __future__ import annotations

import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import traceback as tb
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Patchwright Seeded App", version="0.1.0")

# In-memory log buffer (last 500 entries)
_log_buffer: deque[dict] = deque(maxlen=500)

def _log_error(request: Request, exc: Exception, status_code: int) -> None:
    """Record a structured error log entry."""
    _log_buffer.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR",
        "status_code": status_code,
        "method": request.method,
        "path": str(request.url.path),
        "error_type": type(exc).__name__,
        "message": str(exc),
        "stack_trace": tb.format_exc(),
        "request_id": str(uuid.uuid4()),
    })

# --- Log endpoint (polled by Patchwright monitor) ---
@app.get("/logs")
async def get_logs(since: str = Query(default="")):
    """
    Returns structured log entries since the given ISO timestamp cursor.
    Patchwright polls this endpoint to find failures.
    """
    logs = list(_log_buffer)
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            logs = [
                l for l in logs
                if datetime.fromisoformat(l["timestamp"].replace("Z", "+00:00")) > since_dt
            ]
        except ValueError:
            pass
    return {"logs": logs, "cursor": datetime.now(timezone.utc).isoformat()}

# --- BUG001: KeyError ---
_items_db: dict[int, dict] = {1: {"name": "Widget", "price": 9.99}}

@app.get("/items/{item_id}")
async def get_item(item_id: int, request: Request):
    if item_id not in _items_db:  # Handle case where item is not found
        raise HTTPException(status_code=404, detail="Item not found")
    item = _items_db[item_id]   # BUG: raises KeyError for unknown ids
    return item

# --- BUG002: ZeroDivisionError ---
@app.get("/divide/{a}/{b}")
async def divide(a: int, b: int, request: Request):
    try:
        result = a / b  # BUG: raises ZeroDivisionError when b=0
        return {"result": result}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG003: AttributeError on None ---
_users_db: dict[int, Any] = {1: type("User", (), {"name": "Alice", "email": "a@example.com"})()}

@app.get("/users/{user_id}/profile")
async def get_profile(user_id: int, request: Request):
    try:
        user = _users_db.get(user_id)
        return {"name": user.name}  # BUG: AttributeError if user is None
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG004: IndexError ---
_products: list[dict] = []

@app.get("/products")
async def get_first_product(request: Request):
    try:
        return _products[0]  # BUG: IndexError when list is empty
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG005: TypeError ---
_orders: dict[int, dict] = {1: {"items": [{"price": "10.99"}, {"price": "5.00"}]}}

@app.get("/orders/{order_id}/total")
async def get_order_total(order_id: int, request: Request):
    try:
        order = _orders[order_id]
        total = sum(i["price"] for i in order["items"])  # BUG: sum of strings
        return {"total": total}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG006: ValueError ---
@app.get("/search")
async def search(q: str = Query(default="0"), request: Request = None):
    try:
        page = int(q)  # BUG: ValueError if q is not numeric
        return {"page": page, "results": []}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG007: KeyError in env ---
@app.get("/config")
async def get_config(request: Request):
    try:
        secret = os.environ["MY_SECRET_VALUE"]  # BUG: KeyError if not set
        return {"status": "ok"}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG008: NameError ---
_report_data = {"values": [1, 2, 3]}

@app.get("/reports/daily")
async def daily_report(request: Request):
    try:
        if _report_data["values"]:
            result = sum(_report_data["values"])
        return {"total": result}  # BUG: NameError if values is empty
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG011: ZeroDivisionError in average ---
@app.get("/metrics/average")
async def get_average(request: Request):
    try:
        values: list[float] = []
        avg = sum(values) / len(values)  # BUG: ZeroDivisionError
        return {"average": avg}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG013: AttributeError on None cache ---
_cache: dict | None = None

@app.post("/cache/flush")
async def flush_cache(request: Request):
    try:
        _cache.clear()  # BUG: AttributeError since _cache is None
        return {"status": "flushed"}
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- BUG020: Tricky 4xx that is actually our bug (off-by-one in validation) ---
@app.get("/validate/age")
async def validate_age(age: int, request: Request):
    try:
        if age > 0:  # BUG: should be >= 0 (rejects age=0 which is valid)
            return {"valid": True, "age": age}
        raise HTTPException(status_code=422, detail="Age must be positive")
    except HTTPException:
        raise
    except Exception as e:
        _log_error(request, e, 500)
        raise HTTPException(status_code=500, detail=str(e))

# --- User errors (4xx) — should be ignored by router ---
@app.get("/protected")
async def protected(request: Request):
    auth = request.headers.get("Authorization")
    if not auth:
        # This is a client error — NOT logged as our bug
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return {"status": "ok"}

# --- Infra simulation ---
@app.get("/db/query")
async def db_query(request: Request):
    try:
        raise ConnectionRefusedError("Connection refused: database is down")
    except Exception as e:
        _log_error(request, e, 503)
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/external/api")
async def external_api(request: Request):
    try:
        raise TimeoutError("upstream API timed out after 30s")
    except Exception as e:
        _log_error(request, e, 504)
        raise HTTPException(status_code=504, detail=str(e))

# --- Health ---
@app.get("/health")
async def health():
    return {"status": "ok", "log_count": len(_log_buffer)}