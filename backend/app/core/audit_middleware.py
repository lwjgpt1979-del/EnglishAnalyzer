"""平台级操作审计中间件:admin 后台所有写操作(POST/PUT/PATCH/DELETE)自动留痕。

纯 ASGI 实现(非 BaseHTTPMiddleware,避免读 body 阻塞下游):
- receive 包一层 tee 出请求体(截断 4KB),send 包一层抓响应码;
- 从 Authorization 解 JWT 拿操作人(解不出也记,admin_id=NULL——未授权写尝试也是安全事件);
- 请求体脱敏(password/secret/token/key/ak → ***)后存 JSONB;
- 落库用独立短会话、任何异常吞掉,绝不影响业务请求;
- 排除 /admin/auth/*(登录含明文密码,限流已另行防爆破)。

业务代码零埋点;更细的语义化审计(如电销 sales_audit_log 的 before/after)按域自建。
"""
from __future__ import annotations

import json
import time
import uuid

_MAX_BODY = 4096          # 请求体最多记 4KB
_MAX_QS = 255

# 需要脱敏的字段名(小写精确匹配 或 后缀匹配)
_SENSITIVE_EXACT = {"password", "old_password", "new_password", "secret", "token",
                    "access_token", "refresh_token", "ak", "key", "api_key", "apikey"}
_SENSITIVE_SUFFIX = ("_secret", "_token", "_password")


def _mask(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _SENSITIVE_EXACT or lk.endswith(_SENSITIVE_SUFFIX):
                out[k] = "***"
            else:
                out[k] = _mask(v)
        return out
    if isinstance(obj, list):
        return [_mask(v) for v in obj]
    return obj


# 路径 → 模块归类:与 RBAC 共用同一映射(app/core/module_map.py),口径一致
from app.core.module_map import module_of as _module_of


def _admin_id_from_headers(headers: list[tuple[bytes, bytes]]) -> uuid.UUID | None:
    auth = next((v for k, v in headers if k == b"authorization"), b"").decode("latin1")
    if not auth.startswith("Bearer "):
        return None
    try:
        from app.core.security import decode_token
        payload = decode_token(auth[7:], expected_type="access")
        return uuid.UUID(payload.get("sub"))
    except Exception:  # noqa: BLE001 过期/伪造 token 也照记(admin_id=NULL)
        return None


class AdminAuditMiddleware:
    """记录 /api/v1/admin/* 的写请求。挂在最外层即可,业务无感知。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "")
        path = scope.get("path", "")
        if (method in ("GET", "HEAD", "OPTIONS")
                or "/api/v1/admin/" not in path
                or "/api/v1/admin/auth/" in path):
            return await self.app(scope, receive, send)

        chunks: list[bytes] = []
        got = 0

        async def recv_tee():
            nonlocal got
            msg = await receive()
            if msg["type"] == "http.request" and got < _MAX_BODY:
                b = msg.get("body", b"")
                chunks.append(b[: _MAX_BODY - got])
                got += len(b)
            return msg

        status = {"code": 0}

        async def send_tap(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        t0 = time.monotonic()
        try:
            await self.app(scope, recv_tee, send_tap)
        finally:
            try:
                await self._record(scope, b"".join(chunks), status["code"],
                                   int((time.monotonic() - t0) * 1000))
            except Exception:  # noqa: BLE001 审计失败绝不影响业务
                pass

    async def _record(self, scope, body: bytes, status: int, duration_ms: int) -> None:
        headers = scope.get("headers") or []
        admin_id = _admin_id_from_headers(headers)
        # 请求体:尽量按 JSON 脱敏;非 JSON(如文件上传)只记长度
        detail = None
        if body:
            try:
                detail = _mask(json.loads(body.decode("utf-8")))
            except Exception:  # noqa: BLE001
                detail = {"_non_json_bytes": len(body)}
        xff = next((v for k, v in headers if k == b"x-forwarded-for"), b"").decode("latin1")
        client = scope.get("client")
        ip = (xff.split(",")[0].strip() if xff else (client[0] if client else None))
        qs = (scope.get("query_string") or b"").decode("latin1")[:_MAX_QS] or None

        from app.core.database import _async_session_factory
        from app.models.d9_system import AdminAuditLog
        async with _async_session_factory() as s:
            s.add(AdminAuditLog(
                id=uuid.uuid4(), admin_id=admin_id, method=scope.get("method", ""),
                path=scope.get("path", "")[:255], module=_module_of(scope.get("path", "")),
                status=status, query=qs, detail=detail, ip=ip, duration_ms=duration_ms))
            await s.commit()
