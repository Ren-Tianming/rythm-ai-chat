import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.services.llm import ProviderRegistry
from app.services.upload_limit import UploadBodyLimit


settings = get_settings()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "route", "status", "latency_ms", "user_id", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=getattr(logging, settings.log_level), handlers=[handler], force=True)
logger = logging.getLogger("rythm.api")
logging.getLogger("httpx").setLevel(logging.WARNING)


def error_content(request: Request, code: str, message: str, details: object = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
            "details": details or {},
        }
    }


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.provider_registry = ProviderRegistry(settings)
        yield
        await app.state.provider_registry.aclose()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(UploadBodyLimit, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000)
        if "/documents" in request.url.path or "/messages" in request.url.path:
            response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "route": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", "REQUEST_FAILED"))
            message = str(exc.detail.get("message", "Request failed"))
            details = exc.detail.get("details", {})
        else:
            default_codes = {
                400: "BAD_REQUEST",
                401: "AUTH_SESSION_EXPIRED",
                403: "FORBIDDEN",
                404: "RESOURCE_NOT_FOUND",
                409: "CONFLICT",
                422: "VALIDATION_ERROR",
                429: "RATE_LIMITED",
                503: "SERVICE_UNAVAILABLE",
                504: "MODEL_TIMEOUT",
            }
            code = default_codes.get(exc.status_code, "REQUEST_FAILED")
            message = str(exc.detail)
            details = {}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(request, code, message, details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(item) for item in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_content(
                request, "VALIDATION_ERROR", "Request validation failed", details
            ),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content=error_content(request, "BAD_REQUEST", str(exc)),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_request_error",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "route": request.url.path,
                "status": 500,
                "error_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content=error_content(
                request,
                "INTERNAL_ERROR",
                "An unexpected error occurred",
            ),
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
