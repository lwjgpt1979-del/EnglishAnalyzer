# 微信小程序码 + SMS 邀请实施计划（Plan M）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development

**Goal:** 把当前"显示 6 位邀请码让对方输入"的体验升级为：
1. **微信扫小程序码** → 自动打开对应页面 + 自动填码 + 自动绑定（最佳体验）
2. **短信发邀请码** → 给对方手机号发文字邀请（不便扫码时的兜底）

两个场景：教师邀请学生、学生邀请家人，都支持上述双通道。

**Architecture:**
- **后端**：新 `wechat_service` 管 access_token 缓存（2h TTL）；新 `qrcode_service` 调 `wxacode.getUnlimited` 拿小程序码 buffer 转 base64；`sms_service` 加 `send_invite_sms`。所有外部调用 dev mock 覆盖。
- **API**：`POST /teacher/invite-code/qrcode` 和 `/sms`，`POST /relative/invite-code/qrcode` 和 `/sms`。复用现有 invite-code 生成逻辑（已存在），qrcode/sms 只是不同的"投递方式"。
- **scene 编码**：`t:CODE` 教师邀请，`r:CODE` 家人邀请。短到能塞 wxacode 的 32 字符 scene 限制内。
- **前端 UI**：邀请页面拆 2 按钮（微信码 / 短信）；微信码弹层显示二维码图 + 6 位码兜底 + 复制；短信弹层输入对方手机号 → 发送。
- **接收端**：相应 page 的 `onLoad(options)` 解析 scene 参数 → 自动调 bind。

**Tech Stack:** FastAPI · SQLAlchemy 2.x · httpx · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
新增后端:
  backend/app/services/wechat_service.py             # access_token 缓存
  backend/app/services/qrcode_service.py             # wxacode.getUnlimited
  tests/api/test_qrcode_sms_invite.py

修改后端:
  backend/app/services/sms_service.py                # +send_invite_sms (dev mock)
  backend/app/services/teacher_service.py            # +send_invite_via_sms helper
  backend/app/services/relative_service.py           # +send_invite_via_sms helper
  backend/app/api/v1/teacher.py                      # +2 端点 (qrcode / sms)
  backend/app/api/v1/relative.py                     # +2 端点 (qrcode / sms)
  backend/app/schemas/teacher.py                     # +QRCodeOut, SendInviteSmsRequest
  backend/app/schemas/relative.py                    # 同上

修改前端:
  frontend/miniprogram/src/types/api.ts              # +QRCodeOut
  frontend/miniprogram/src/api/teacher.ts            # +genQrcode, sendInviteSms
  frontend/miniprogram/src/api/relative.ts           # 同上
  frontend/miniprogram/src/pages/teacher/students.vue   # 邀请区改两按钮 + 弹层
  frontend/miniprogram/src/pages/profile/index.vue   # 家人邀请区改两按钮 + 弹层
  frontend/miniprogram/src/pages/teacher/students.vue   # onLoad 加 scene 自动绑
  frontend/miniprogram/src/pages/relative/center.vue    # onLoad 加 scene 自动绑
```

**Key 微信 API 速查：**
- access_token：`GET https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=XX&secret=XX` → `{access_token, expires_in:7200}`
- 小程序码：`POST https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token=XX` body `{scene, page, check_path:false, env_version:"trial"|"release"}` → image binary
- scene **最大 32 字符**，仅支持 `a-zA-Z0-9` + `!#$&'()*+,/:;=?@-._~` —— 我们 `t:CODE` 和 `r:CODE` 8 字符内安全
- dev 阶段 / 未发布版：env_version="trial"，**只有该小程序的体验者扫码有效**

---

## Task 0: 后端 wechat_service + qrcode_service + sms 邀请扩展 + 7 个测试

**Files:**
- Create: `backend/app/services/wechat_service.py`
- Create: `backend/app/services/qrcode_service.py`
- Modify: `backend/app/services/sms_service.py`
- Create: `tests/api/test_qrcode_sms_invite.py`

- [ ] **Step 1: 创建 `backend/app/services/wechat_service.py`**

```python
"""微信 access_token 缓存（D-078 / Plan M）。

access_token 2h 有效，全局共享。简单内存缓存（多 worker 部署时各自缓存独立，可接受——
单 worker 也用得了。生产高并发可换 Redis）。

dev 模式（wechat_appid 以 'wx_dev' 开头）：返回 mock token，不真调微信。
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

_TOKEN_REFRESH_BEFORE_SECONDS = 600  # 提前 10 分钟刷新
_DEV_MOCK_TOKEN = "dev_mock_access_token_AAAAA"

_cache: dict[str, float | str] = {"token": "", "expires_at": 0.0}


def _is_dev_mode() -> bool:
    return settings.wechat_appid.startswith("wx_dev")


async def get_access_token() -> str:
    """返回 access_token。缓存未过期则直接返回；否则刷新。"""
    if _is_dev_mode():
        return _DEV_MOCK_TOKEN

    now = time.time()
    expires_at = float(_cache.get("expires_at", 0))
    if _cache.get("token") and now + _TOKEN_REFRESH_BEFORE_SECONDS < expires_at:
        return str(_cache["token"])

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
            },
        )
    data = resp.json()
    if "access_token" not in data:
        raise AppError(code=502, message=f"微信 access_token 获取失败：{data}")

    _cache["token"] = data["access_token"]
    _cache["expires_at"] = now + int(data["expires_in"])
    return str(_cache["token"])
```

- [ ] **Step 2: 创建 `backend/app/services/qrcode_service.py`**

```python
"""微信小程序码生成（D-078 / Plan M）。

调 wxacode.getUnlimited 拿 PNG buffer → base64 返回。
dev 模式：返回 picsum 占位图 base64，前端能显示但扫码无效（开发自测够用）。
"""
from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.wechat_service import _is_dev_mode, get_access_token

_PICSUM_DEV_FALLBACK_URL = "https://picsum.photos/seed/qrcode/280/280.jpg"


async def get_miniprogram_qrcode_base64(
    *,
    scene: str,
    page: str,
    env_version: str = "trial",
) -> str:
    """返回小程序码的 base64 字符串（不含 data: 前缀）。

    Args:
        scene: 场景值，最大 32 字符（如 't:ABC123' 或 'r:DEF456'）
        page: 目标页面（如 'pages/teacher/students'）；不存在则错
        env_version: 'develop' / 'trial' / 'release'，dev 阶段填 'trial'
    """
    if len(scene) > 32:
        raise AppError(code=400, message=f"scene 长度超过 32：{scene}")

    if _is_dev_mode():
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(_PICSUM_DEV_FALLBACK_URL)
        return base64.b64encode(r.content).decode("ascii")

    token = await get_access_token()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={token}",
            json={
                "scene": scene,
                "page": page,
                "check_path": False,
                "env_version": env_version,
            },
        )

    # 微信成功返回 image binary，失败返回 JSON
    if resp.headers.get("content-type", "").startswith("image"):
        return base64.b64encode(resp.content).decode("ascii")

    err = resp.json()
    raise AppError(code=502, message=f"微信小程序码生成失败：{err}")
```

- [ ] **Step 3: 扩展 `backend/app/services/sms_service.py`，加 `send_invite_sms`**

末尾追加：
```python


async def send_invite_sms(
    *,
    phone: str,
    code: str,
    inviter_name: str,
    role: str,  # 'teacher' or 'relative'
) -> None:
    """发送邀请短信。dev mode 仅记日志。"""
    role_text = "老师" if role == "teacher" else "家人"
    page_text = "教师中心" if role == "teacher" else "家人中心"
    content = (
        f"【engGramer】{inviter_name}邀请您加入"
        f"，邀请码 {code}（24h有效）。"
        f"请在小程序-我的-{page_text} 输入此码完成绑定。"
    )
    if _is_dev_mode():
        logger.warning("[SMS DEV MOCK invite] phone=%s role=%s content=%s", phone, role, content)
        return
    # 生产：替换 _send_real_sms 实现（阿里云/腾讯云短信通知模板）
    await _send_real_sms(phone=phone, code=code, purpose=f"invite_{role}")
```

- [ ] **Step 4: 创建 `tests/api/test_qrcode_sms_invite.py`**

```python
"""微信码 + SMS 邀请测试（D-078 / Plan M）。"""
import base64
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.wechat_service import get_access_token, _DEV_MOCK_TOKEN


@pytest.mark.asyncio
async def test_wechat_access_token_dev_mock():
    """dev appid 触发 mock token。"""
    token = await get_access_token()
    assert token == _DEV_MOCK_TOKEN


@pytest.mark.asyncio
async def test_qrcode_dev_mock_returns_base64():
    """dev 模式返回 picsum base64，前端能渲染。"""
    b64 = await get_miniprogram_qrcode_base64(
        scene="t:ABC123", page="pages/teacher/students",
    )
    # 验证是合法 base64
    decoded = base64.b64decode(b64)
    assert len(decoded) > 100  # 至少是一张图


@pytest.mark.asyncio
async def test_qrcode_scene_too_long_400():
    """scene 超 32 字符报 400。"""
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc:
        await get_miniprogram_qrcode_base64(
            scene="a" * 33, page="pages/teacher/students",
        )
    assert exc.value.code == 400


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"qrc_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _setup_teacher(client: AsyncClient, suffix: str) -> dict:
    headers = await _login(client, suffix)
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers)
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://x.test/c.jpg"}, headers=headers,
    )
    return headers


@pytest.mark.asyncio
async def test_teacher_qrcode_endpoint(client):
    """老师调 qrcode 接口拿到 base64 + code。"""
    h = await _setup_teacher(client, f"q_t_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/teacher/invite-code/qrcode", headers=h)
    assert r.status_code == 200
    d = r.json()["data"]
    assert len(d["code"]) == 6
    assert len(d["qrcode_base64"]) > 100  # base64 串


@pytest.mark.asyncio
async def test_teacher_sms_endpoint(client):
    """老师调 sms 接口：dev mode 日志，返回成功。"""
    h = await _setup_teacher(client, f"q_t_s_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/teacher/invite-code/sms",
        json={"phone": "13900000000"}, headers=h,
    )
    assert r.status_code == 200
    assert r.json()["data"]["sent"] is True
    assert len(r.json()["data"]["code"]) == 6


@pytest.mark.asyncio
async def test_relative_qrcode_and_sms(client):
    """学生（非老师）调 relative qrcode + sms。"""
    h = await _login(client, f"q_r_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1995, "agreement_version": "v1.0"}, headers=h,
    )
    r1 = await client.post("/api/v1/relative/invite-code/qrcode", headers=h)
    assert r1.status_code == 200
    assert len(r1.json()["data"]["qrcode_base64"]) > 100

    r2 = await client.post(
        "/api/v1/relative/invite-code/sms",
        json={"phone": "13900000001"}, headers=h,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["sent"] is True
```

- [ ] **Step 5: 跑测试 + 全量**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_qrcode_sms_invite.py -v
python -m pytest ../tests/ -q
```
Expected: 7 PASS（3 unit + 4 API），全量 ≥ 223 PASS。

**注意**：test_qrcode_dev_mock_returns_base64 需要访问 picsum.photos，若 CI 无外网会失败。可加 skip 标记或用更小的 stub。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/wechat_service.py backend/app/services/qrcode_service.py \
        backend/app/services/sms_service.py tests/api/test_qrcode_sms_invite.py
git commit -m "feat(invite): wechat access_token cache + wxacode qrcode + invite sms service"
```

---

## Task 1: 后端 schemas + 4 API 端点（teacher 2 + relative 2）

**Files:**
- Modify: `backend/app/schemas/teacher.py`
- Modify: `backend/app/schemas/relative.py`
- Modify: `backend/app/api/v1/teacher.py`
- Modify: `backend/app/api/v1/relative.py`

- [ ] **Step 1: schemas/teacher.py 加**

末尾追加：
```python
class QRCodeOut(BaseModel):
    code: str
    expires_at: datetime
    qrcode_base64: str = Field(..., description="PNG/JPEG base64，前端用 data: 前缀展示")


class SendInviteSmsRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)


class SendInviteSmsOut(BaseModel):
    sent: bool
    code: str  # 仍返回 code 让发送者也能看到、复制
```

- [ ] **Step 2: schemas/relative.py 加**

末尾追加（与 teacher 相同结构，可重用 import）：
```python
from app.schemas.teacher import QRCodeOut, SendInviteSmsRequest, SendInviteSmsOut  # noqa: F401
```

或者各自定义一遍（更明确，无跨域 import）。本任务用第二种：在 relative.py 复制一份同名 class。

- [ ] **Step 3: teacher.py 加 2 端点（在 create_invite_code 端点附近）**

```python
from app.schemas.teacher import QRCodeOut, SendInviteSmsRequest, SendInviteSmsOut
from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.sms_service import send_invite_sms


@router.post("/invite-code/qrcode", response_model=BaseResponse[QRCodeOut])
async def teacher_invite_qrcode(db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(db, teacher_id=current_user.id)
    await db.commit()
    qb64 = await get_miniprogram_qrcode_base64(
        scene=f"t:{invite.code}",
        page="pages/teacher/students",
    )
    return make_ok(QRCodeOut(
        code=invite.code, expires_at=invite.expires_at, qrcode_base64=qb64,
    ))


@router.post("/invite-code/sms", response_model=BaseResponse[SendInviteSmsOut])
async def teacher_invite_sms(body: SendInviteSmsRequest, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(db, teacher_id=current_user.id)
    await db.commit()
    await send_invite_sms(
        phone=body.phone, code=invite.code,
        inviter_name=current_user.nickname or "您的老师",
        role="teacher",
    )
    return make_ok(SendInviteSmsOut(sent=True, code=invite.code))
```

- [ ] **Step 4: relative.py 加 2 端点（类似教师，但 scene 是 `r:`，page 是 `pages/relative/center`）**

```python
from app.schemas.relative import QRCodeOut, SendInviteSmsRequest, SendInviteSmsOut
from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.sms_service import send_invite_sms


@router.post("/invite-code/qrcode", response_model=BaseResponse[QRCodeOut])
async def relative_invite_qrcode(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    qb64 = await get_miniprogram_qrcode_base64(
        scene=f"r:{invite.code}",
        page="pages/relative/center",
    )
    return make_ok(QRCodeOut(
        code=invite.code, expires_at=invite.expires_at, qrcode_base64=qb64,
    ))


@router.post("/invite-code/sms", response_model=BaseResponse[SendInviteSmsOut])
async def relative_invite_sms(body: SendInviteSmsRequest, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    await send_invite_sms(
        phone=body.phone, code=invite.code,
        inviter_name=current_user.nickname or "您的家人",
        role="relative",
    )
    return make_ok(SendInviteSmsOut(sent=True, code=invite.code))
```

- [ ] **Step 5: 跑测试 + 全量**

```bash
python -m pytest ../tests/api/test_qrcode_sms_invite.py -v
python -m pytest ../tests/ -q
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/teacher.py backend/app/schemas/relative.py \
        backend/app/api/v1/teacher.py backend/app/api/v1/relative.py
git commit -m "feat(invite): 4 endpoints — teacher/relative invite-code qrcode + sms"
```

---

## Task 2: 前端 API + 类型 + 教师中心邀请 UI

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/api/teacher.ts`
- Modify: `frontend/miniprogram/src/api/relative.ts`
- Modify: `frontend/miniprogram/src/pages/teacher/students.vue`

- [ ] **Step 1: types/api.ts 加类型**

```typescript
export interface QRCodeOut {
  code: string
  expires_at: string
  qrcode_base64: string
}

export interface SendInviteSmsOut {
  sent: boolean
  code: string
}
```

- [ ] **Step 2: api/teacher.ts 加 2 函数**

```typescript
export function teacherInviteQrcode() {
  return request('/api/v1/teacher/invite-code/qrcode', { method: 'POST' })
}

export function teacherInviteSms(phone: string) {
  return request('/api/v1/teacher/invite-code/sms', { method: 'POST', data: { phone } })
}
```

- [ ] **Step 3: api/relative.ts 加 2 函数**

```typescript
export function relativeInviteQrcode() {
  return request('/api/v1/relative/invite-code/qrcode', { method: 'POST' })
}

export function relativeInviteSms(phone: string) {
  return request('/api/v1/relative/invite-code/sms', { method: 'POST', data: { phone } })
}
```

- [ ] **Step 4: pages/teacher/students.vue 改"邀请学生绑定"卡片**

把原"生成邀请码"按钮改成两按钮 + 弹层：

```vue
    <view v-if="isTeacher && certStatus === 'certified'" class="card">
      <view class="card-title">邀请学生绑定</view>
      <view class="invite-actions">
        <button class="btn-primary half" :disabled="loadingQr" @tap="onGenQr">
          {{ loadingQr ? '生成中…' : '微信扫码' }}
        </button>
        <button class="btn-secondary half" @tap="showSmsDialog = true">短信邀请</button>
      </view>

      <!-- 二维码弹层 -->
      <view v-if="qr" class="modal" @tap.self="qr = null">
        <view class="modal-card">
          <image class="qr-img" :src="'data:image/png;base64,' + qr.qrcode_base64" mode="aspectFit" />
          <text class="qr-tip">让学生用微信扫一扫，自动打开小程序并绑定您。</text>
          <view class="qr-fallback">
            <text>或手动输入邀请码：</text>
            <text class="qr-code">{{ qr.code }}</text>
            <button size="mini" class="btn-copy" @tap="copyCode(qr.code)">复制</button>
          </view>
          <button class="btn-secondary" @tap="qr = null">关闭</button>
        </view>
      </view>

      <!-- 短信弹层 -->
      <view v-if="showSmsDialog" class="modal" @tap.self="showSmsDialog = false">
        <view class="modal-card">
          <view class="card-title">短信邀请</view>
          <input v-model="smsPhone" class="input" placeholder="对方手机号" maxlength="11" />
          <text class="dev-hint">将给该手机号发送邀请码短信。</text>
          <button class="btn-primary" :disabled="smsSending || smsPhone.length !== 11" @tap="onSendSms">
            {{ smsSending ? '发送中…' : '发送' }}
          </button>
          <button class="btn-secondary" @tap="showSmsDialog = false">取消</button>
        </view>
      </view>
    </view>
```

script 加：
```typescript
import { teacherInviteQrcode, teacherInviteSms } from '@/api/teacher'
const qr = ref<{ code: string; qrcode_base64: string; expires_at: string } | null>(null)
const loadingQr = ref(false)
const showSmsDialog = ref(false)
const smsPhone = ref('')
const smsSending = ref(false)

async function onGenQr() {
  loadingQr.value = true
  try { const r: any = await teacherInviteQrcode(); qr.value = r }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { loadingQr.value = false }
}

async function onSendSms() {
  smsSending.value = true
  try {
    await teacherInviteSms(smsPhone.value)
    uni.showToast({ title: '短信已发送', icon: 'success' })
    showSmsDialog.value = false; smsPhone.value = ''
  } catch (e: any) {
    uni.showToast({ title: e?.message || '发送失败', icon: 'none' })
  } finally { smsSending.value = false }
}

function copyCode(c: string) {
  uni.setClipboardData({ data: c, success: () => uni.showToast({ title: '已复制', icon: 'success' }) })
}
```

样式追加（黄油风）：
```css
.invite-actions { display: flex; gap: 12rpx; }
.half { flex: 1; margin-top: 0; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
.modal-card { background: var(--c-bg-card); border-radius: var(--r-xl); padding: var(--sp-5); width: 80%; max-width: 600rpx; box-shadow: 0 8rpx 32rpx rgba(0,0,0,.2); }
.qr-img { width: 100%; height: 480rpx; }
.qr-tip { display: block; text-align: center; font-size: 26rpx; color: var(--c-text-second); margin: 16rpx 0; line-height: 1.5; }
.qr-fallback { display: flex; align-items: center; gap: 12rpx; margin: 16rpx 0; padding: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); }
.qr-code { flex: 1; font-size: 36rpx; font-weight: 800; letter-spacing: 4rpx; color: var(--c-ink); }
.btn-copy { background: var(--c-primary); color: var(--c-ink); font-size: 24rpx; font-weight: 600; border-radius: var(--r-sm); padding: 8rpx 16rpx; }
.input { width: 100%; border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin: 16rpx 0 8rpx; box-sizing: border-box; }
.dev-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
```

把原 `handleGenerateCode` 等老逻辑保留还是删？**保留** old 6 位码生成函数没坏处（前向兼容），但 UI 不再触发。或者删掉，让按钮全部走新流程。本任务保险起见 **删旧 UI**（已上面的新模板替换），保留 service 不动。

- [ ] **Step 5: pages/profile/index.vue 改"邀请家人绑定"区**

把原"生成邀请码"按钮换成两按钮 + 弹层（结构同上但 API 改 `relativeInviteQrcode` / `relativeInviteSms`）。

```vue
    <!-- 邀请家人 -->
    <view class="card">
      <view class="card-title">邀请家人绑定</view>
      <text class="menu-desc">家长用微信扫小程序码自动绑定；或短信发邀请码。</text>
      <view class="invite-actions">
        <button class="btn-primary half" :disabled="loadingQr" @tap="onGenRelQr">
          {{ loadingQr ? '生成中…' : '微信扫码' }}
        </button>
        <button class="btn-secondary half" @tap="showRelSms = true">短信邀请</button>
      </view>

      <view v-if="relQr" class="modal" @tap.self="relQr = null">
        <view class="modal-card">
          <image class="qr-img" :src="'data:image/png;base64,' + relQr.qrcode_base64" mode="aspectFit" />
          <text class="qr-tip">家长用微信扫一扫，自动打开并绑定。</text>
          <view class="qr-fallback">
            <text>或手动输入：</text><text class="qr-code">{{ relQr.code }}</text>
            <button size="mini" class="btn-copy" @tap="copyRelCode">复制</button>
          </view>
          <button class="btn-secondary" @tap="relQr = null">关闭</button>
        </view>
      </view>

      <view v-if="showRelSms" class="modal" @tap.self="showRelSms = false">
        <view class="modal-card">
          <view class="card-title">短信邀请家人</view>
          <input v-model="relSmsPhone" class="input" placeholder="家人手机号" maxlength="11" />
          <button class="btn-primary" :disabled="relSmsSending || relSmsPhone.length !== 11" @tap="onSendRelSms">
            {{ relSmsSending ? '发送中…' : '发送' }}
          </button>
          <button class="btn-secondary" @tap="showRelSms = false">取消</button>
        </view>
      </view>
    </view>
```

script 加（与 teacher 同 pattern）：
```typescript
import { relativeInviteQrcode, relativeInviteSms } from '@/api/relative'
const relQr = ref<any>(null)
const loadingQr = ref(false)
const showRelSms = ref(false)
const relSmsPhone = ref('')
const relSmsSending = ref(false)
async function onGenRelQr() { loadingQr.value = true; try { relQr.value = await relativeInviteQrcode() as any } catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) } finally { loadingQr.value = false } }
async function onSendRelSms() { relSmsSending.value = true; try { await relativeInviteSms(relSmsPhone.value); uni.showToast({ title: '短信已发送', icon: 'success' }); showRelSms.value = false; relSmsPhone.value = '' } catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) } finally { relSmsSending.value = false } }
function copyRelCode() { if (relQr.value) uni.setClipboardData({ data: relQr.value.code, success: () => uni.showToast({ title: '已复制', icon: 'success' }) }) }
```

样式（同 teacher 那套 modal/qr-img 等，复用即可）。

把现有的"生成邀请码 / 重新生成 / 显示 6 位码"全删，统一走 modal。

- [ ] **Step 6: 提交前端**

```bash
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/teacher.ts frontend/miniprogram/src/api/relative.ts \
        frontend/miniprogram/src/pages/teacher/students.vue \
        frontend/miniprogram/src/pages/profile/index.vue
git commit -m "feat(invite): frontend — qrcode + sms invite UI (teacher + relative)"
```

---

## Task 3: 扫码接收端 onLoad 解析 scene 自动绑定

**Files:**
- Modify: `frontend/miniprogram/src/pages/teacher/students.vue`（学生扫老师的码自动绑）
- Modify: `frontend/miniprogram/src/pages/relative/center.vue`（家长扫学生的码自动绑）

- [ ] **Step 1: pages/teacher/students.vue 改 onMounted/onLoad 解析 scene**

uni-app 小程序里 onLoad 可以这样接收 query：
```typescript
import { onLoad } from '@dcloudio/uni-app'
import { bindTeacher } from '@/api/teacher'

onLoad((options) => {
  // 扫码进入：options.scene 是 URL-encoded 字符串
  const sceneRaw = (options as any)?.scene
  if (!sceneRaw) return
  const scene = decodeURIComponent(sceneRaw)
  if (!scene.startsWith('t:')) return
  const code = scene.slice(2)
  if (!code) return

  // 自动调老师邀请码绑定
  uni.showLoading({ title: '正在绑定老师…' })
  bindTeacher(code)
    .then(() => { uni.hideLoading(); uni.showToast({ title: '绑定成功', icon: 'success' }) })
    .catch((e: any) => {
      uni.hideLoading()
      uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
    })
})
```

- [ ] **Step 2: pages/relative/center.vue 同理（scene `r:CODE` → 自动 bindRelative，但需要 relationship 字段，先 prompt 关系名）**

```typescript
import { onLoad } from '@dcloudio/uni-app'
import { bindRelative } from '@/api/relative'

onLoad((options) => {
  const sceneRaw = (options as any)?.scene
  if (!sceneRaw) return
  const scene = decodeURIComponent(sceneRaw)
  if (!scene.startsWith('r:')) return
  const code = scene.slice(2)
  if (!code) return

  // 关系需要用户填，弹 prompt
  uni.showModal({
    title: '请填写您与孩子的关系',
    editable: true,
    placeholderText: '如：母亲 / 父亲 / 祖父',
    success: async (res) => {
      if (!res.confirm || !res.content?.trim()) return
      uni.showLoading({ title: '绑定中…' })
      try {
        await bindRelative(code, res.content.trim())
        uni.hideLoading()
        uni.showToast({ title: '绑定成功', icon: 'success' })
      } catch (e: any) {
        uni.hideLoading()
        uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
      }
    },
  })
})
```

- [ ] **Step 3: 提交**

```bash
git add frontend/miniprogram/src/pages/teacher/students.vue \
        frontend/miniprogram/src/pages/relative/center.vue
git commit -m "feat(invite): scan-to-bind — onLoad parses scene and auto-binds"
```

---

## Task 4: 集成验证 + 归档 D-078 + push

- [ ] **Step 1: 全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -q
```
Expected: ≥ 223 PASS（216 + 7 新增）

- [ ] **Step 2: live server 端点冒烟**

```bash
uvicorn app.main:app --port 8030 --log-level warning &
UVICORN_PID=$!
sleep 3
curl -s http://localhost:8030/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
paths = sorted([p for p in spec['paths'].keys() if 'qrcode' in p or 'sms' in p])
print('Plan M 端点:')
for p in paths: print('  ', p)
"
kill $UVICORN_PID 2>/dev/null
```
Expected: 4 个新端点

- [ ] **Step 3: 归档 D-078（插入在 D-077 之前）**

```markdown
## D-078｜邀请双通道：微信小程序码 + 短信邀请

**日期：** 2026-05-30
**背景：** D-076 已实现"6 位邀请码手输绑定"，但 UX 较弱（家长/学生需在两个 App 间手动复制）。升级为：①微信小程序码扫码自动绑定（最佳体验）②短信发邀请码（兜底）。教师邀请学生 + 学生邀请家人，两端都支持双通道。
**结论：**
1. **微信 access_token 缓存：** 新 `wechat_service.get_access_token`，内存缓存 2h - 10min 提前刷新；dev 模式（appid 以 wx_dev 开头）返回 mock。
2. **小程序码生成：** 新 `qrcode_service.get_miniprogram_qrcode_base64`，调 wxacode.getUnlimited（POST /wxa/getwxacodeunlimit），scene 格式 `t:CODE` / `r:CODE`，page 分别指向 `pages/teacher/students` / `pages/relative/center`，env_version=trial（开发版本）；dev 模式返回 picsum 占位图 base64（开发者能看到图但扫不出小程序）。
3. **SMS 邀请：** sms_service 加 `send_invite_sms(phone, code, inviter_name, role)`，发送通知模板内容（含邀请码 + 引导文案）；dev 模式日志打印；生产前需接阿里云/腾讯云短信模板。
4. **API（4 个）：** `/teacher/invite-code/qrcode` 和 `/sms`；`/relative/invite-code/qrcode` 和 `/sms`。复用现有 `generate_invite_code` 逻辑（已存在），qrcode/sms 只是不同投递方式。
5. **前端 UI：** 教师中心 + profile 家人卡片各拆两按钮"微信扫码 / 短信邀请" + modal 弹层（二维码 + 6 位码兜底 + 复制按钮 + 关闭）。修改后旧"6 位码直显"UI 删除，统一走 modal。
6. **接收端自动绑定：** `pages/teacher/students.vue` 和 `pages/relative/center.vue` 的 `onLoad(options)` 解析 `scene`（URL decode 后），前缀 `t:` 调 bindTeacher、`r:` 调 bindRelative；relative 需要 relationship，用 `uni.showModal({editable:true})` 弹输入框。
7. **测试：** 7 个测试（3 unit + 4 API），全量 ≥ 223 PASS。
**已知限制：** 
- env_version=trial 阶段仅小程序开发者/体验者扫码有效；上线后所有微信用户可扫。
- SMS 走 dev mock；生产前必须实现 `_send_real_sms` 并在阿里云/腾讯云配置通知短信模板（区别于验证码模板）。
- DevTools 测试扫码场景：模拟器顶部"自定义编译" → 启动页选 students/center → 启动参数填 `scene=t%3AABC123` 模拟扫码。
**影响范围：** 2 个新 service + 1 个 service 扩展 + 4 个新 API 端点 + 4 个前端文件改动；测试 +7；已推送 GitHub main 分支。

---
```

- [ ] **Step 4: 提交 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-078 — wechat qrcode + sms invite"
git push
```

---

## Self-Review

### Spec 覆盖
| 用户需求 | 实现 |
|---|---|
| 老师邀请学生：微信扫码 | Task 0+1+2：wxacode + students 弹层 |
| 老师邀请学生：短信发码 | Task 0+1+2：sms_service + 弹层 |
| 学生邀请家人：微信扫码 | Task 0+1+2：wxacode + profile 弹层 |
| 学生邀请家人：短信发码 | Task 0+1+2：sms_service + 弹层 |
| 扫码自动绑定 | Task 3：onLoad scene 解析 + 自动调 bind |

### 类型一致性
- scene 格式约定 `t:CODE` / `r:CODE` 在后端生成、前端解析处保持一致
- QRCodeOut 字段在 teacher / relative schema 同结构
- SendInviteSmsOut 同上

### Placeholder
- access_token：dev mock 已覆盖
- wxacode：dev 返回 picsum 占位图（前端能渲染）
- SMS：dev 日志打印
- 生产前需关 `_send_real_sms` placeholder + 微信 access_token 真调通
