import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.v1 import classify, graphs, health, papers
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.services.inference import InferenceService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with httpx.AsyncClient() as client:
            application.state.http = client
            yield

    application = FastAPI(title="ResearchGraph API", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.inference = InferenceService(settings.model_artifact_dir)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Invalid request",
                        "details": details,
                    }
                }
            ),
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        logger.error("Unhandled API error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "internal_error", "message": "An internal server error occurred"}
            },
        )

    for router in (health.router, papers.router, classify.router, graphs.router):
        application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
