"""Day 5 ASGI app: liveness and shared HTTP infrastructure only."""

from fastapi import FastAPI

from sales_manager_api.errors import install_error_handlers
from sales_manager_api.middleware import RequestContextMiddleware
from sales_manager_api.schemas import HealthResponse
from sales_manager_api.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Sales Manager API",
        debug=False,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings if settings is not None else load_settings()
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health", response_model=HealthResponse, operation_id="getHealth")
    async def health() -> HealthResponse:
        # Liveness must not depend on credentials or external AWS availability.
        return HealthResponse()

    return app
