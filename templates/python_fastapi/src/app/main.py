from __future__ import annotations

import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="AutoDev App")

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response

@app.get("/health")
def health():
    return {"ok": True}

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "BAD_REQUEST", "message": str(exc)}},
    )
