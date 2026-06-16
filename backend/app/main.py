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

    # CORS：dev 默认放开；生产用 settings.cors_allow_origins（逗号分隔域名）收紧。
    # 通配 "*" 与 allow_credentials=True 在浏览器侧不兼容，故仅显式域名时才带 credentials。
    _origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    _wildcard = _origins == ["*"] or not _origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if _wildcard else _origins,
        allow_credentials=not _wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 行为埋点（§5.5 DAU/MAU）：按 token 记录日活，进程内去重，失败不影响请求
    @app.middleware("http")
    async def _activity_mw(request, call_next):
        response = await call_next(request)
        try:
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                from app.core.security import decode_token
                from app.services import activity_service
                payload = decode_token(auth[7:], expected_type="access")
                uid = payload.get("sub")
                if uid:
                    await activity_service.record(uid)
        except Exception:  # noqa: BLE001
            pass
        return response

    # Unified exception handling
    register_exception_handlers(app)

    # API routes
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
