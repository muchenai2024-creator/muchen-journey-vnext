import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from journey_api.config import get_settings
from journey_api.errors import ApiError
from journey_api.identity_routes import router as identity_router
from journey_api.outcome_routes import router as outcome_router
from journey_api.ops_routes import router as ops_router
from journey_api.review_routes import router as review_router
from journey_api.routes import router
from journey_api.submission_routes import router as submission_router

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

docs_enabled = settings.app_env in {"local", "test"}
app = FastAPI(
    title="Muchen Journey vNext API",
    version="0.2.0-local",
    docs_url="/docs" if docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs_enabled else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else f"req_{uuid.uuid4().hex}"
    )
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "retryable": exc.retryable,
            },
            "request_id": getattr(request.state, "request_id", "req_unknown"),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_details = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "请求内容不符合合同。",
                "details": {"fields": safe_details},
                "retryable": False,
            },
            "request_id": getattr(request.state, "request_id", "req_unknown"),
        },
    )


app.include_router(router)
app.include_router(submission_router)
app.include_router(identity_router)
app.include_router(review_router)
app.include_router(outcome_router)
app.include_router(ops_router)
