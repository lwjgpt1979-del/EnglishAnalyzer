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
    # 续跑因重启而中断的教材生成任务(方案 A;persist 幂等,跳过已成功单元)
    try:
        from app.services.curriculum_gen_service import resume_running_jobs
        await resume_running_jobs()
        from app.services.real_extract_service import resume_running_jobs as _resume_extract
        await _resume_extract()
    except Exception:  # noqa: BLE001
        pass
    # 预热 LLM 生效模型缓存(后台「模型配置」页可改,无需重启)
    try:
        from app.core.database import async_session_factory
        from app.services import llm_config_service
        async with async_session_factory() as _db:
            await llm_config_service.get_model(_db)
    except Exception:  # noqa: BLE001
        pass
    yield
    # shutdown: release connection pool
    await close_async_engine()


def _init_sentry() -> None:
    """错误监控（上线硬化）：配了 SENTRY_DSN 才启用；未装包/未配则静默跳过。"""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        print("⚠️ SENTRY_DSN 已配置但未安装 sentry-sdk，跳过（pip install sentry-sdk）", flush=True)
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,   # 不上报用户 PII
    )
    print(f"✅ Sentry 已启用（env={settings.environment}）", flush=True)


def create_app() -> FastAPI:
    _init_sentry()
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
