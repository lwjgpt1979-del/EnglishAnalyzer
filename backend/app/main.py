from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import close_async_engine
from app.core.exceptions import register_exception_handlers
from app.core.safety import run_production_safety_check


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: async engine already initialized at module-level in database.py
    # 生产环境配置安全检查（D-077）：debug=False 时检测 placeholder，命中则 fail-fast
    run_production_safety_check(settings)
    yield
    # shutdown: release connection pool
    await close_async_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="engGramer API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS (open for dev, tighten for production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Unified exception handling
    register_exception_handlers(app)

    # API routes
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
