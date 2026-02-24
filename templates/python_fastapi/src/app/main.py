from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.models import ErrorDetail, ErrorResponse, HealthResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="AutoDev App")


def _error_response(code: str, message: str, details: dict[str, Any] | None = None) -> ErrorResponse:
    return ErrorResponse(error=ErrorDetail(code=code, message=message, details=details or {}))


def _to_payload(response: ErrorResponse) -> dict[str, Any]:
    return response.model_dump() if hasattr(response, "model_dump") else response.dict()


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req-{uuid.uuid4()}"
    request.state.request_id = request_id
    logger.info("request.start", extra={"request_id": request_id, "path": str(request.url.path), "method": request.method})
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request.finish",
        extra={"request_id": request_id, "status_code": response.status_code, "path": str(request.url.path)},
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


class EchoPayload(BaseModel):
    payload: str = Field(...)
    repeat: int = Field(1, ge=1, le=3)


class EchoResponse(BaseModel):
    payload: str
    repeats: int
    values: list[str]


@app.post("/echo", response_model=EchoResponse)
def echo(payload: EchoPayload) -> EchoResponse:
    values = [payload.payload for _ in range(payload.repeat)]
    return EchoResponse(payload=payload.payload, repeats=payload.repeat, values=values)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    request_id = getattr(request.state, "request_id", request.headers.get("x-request-id", "req-unknown"))
    logger.warning(
        "request.value_error",
        extra={"request_id": request_id, "message": str(exc), "path": str(request.url.path)},
    )
    response = _error_response(
        code="BAD_REQUEST",
        message=str(exc),
        details={"path": str(request.url.path)},
    )
    return JSONResponse(status_code=400, content=_to_payload(response), headers={"x-request-id": request_id})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", request.headers.get("x-request-id", "req-unknown"))
    logger.warning("request.validation_error", extra={"request_id": request_id, "errors": len(exc.errors())})
    response = _error_response(
        code="INVALID_REQUEST",
        message="Request validation failed",
        details={"errors": exc.errors(), "path": str(request.url.path)},
    )
    return JSONResponse(status_code=422, content=_to_payload(response), headers={"x-request-id": request_id})


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", request.headers.get("x-request-id", "req-unknown"))
    logger.exception(
        "request.unhandled",
        extra={"request_id": request_id, "path": str(request.url.path)},
    )
    response = _error_response(code="INTERNAL_ERROR", message="Unexpected error", details={"path": str(request.url.path)})
    return JSONResponse(status_code=500, content=_to_payload(response), headers={"x-request-id": request_id})
