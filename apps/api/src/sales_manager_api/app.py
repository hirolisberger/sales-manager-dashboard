"""ASGI app: liveness, shared infrastructure and local product operations."""

from secrets import token_bytes

from fastapi import FastAPI

from sales_manager_api.errors import install_error_handlers
from sales_manager_api.middleware import RequestContextMiddleware
from sales_manager_api.product_routes import router as product_router
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
    # Local-only cursors expire after restart; persistent secrets come with deployment.
    app.state.product_cursor_key = token_bytes(32)
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(product_router)

    @app.get("/health", response_model=HealthResponse, operation_id="getHealth")
    async def health() -> HealthResponse:
        # Liveness must not depend on credentials or external AWS availability.
        return HealthResponse()

    return app
