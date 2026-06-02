# Plan G — OCR 识别管道：阿里云（印刷体）+ 腾讯云（手写体）→ DeepSeek 结构化解析

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学生上传试卷图片后自动触发双引擎 OCR（阿里云读光识别印刷体题目、腾讯云识别手写作答），两路原始文字经 DeepSeek 结构化解析后写入 `question_text / student_answer / correct_answer`，从而为 AI 诊断分析提供真实内容。

**Architecture:** 上传图片后立即触发 FastAPI `BackgroundTask`：图片 URL 并行送入两路 OCR API，原始文字拼合后送入 DeepSeek 解析出结构化字段，结果写回 `WrongQuestion` 并记录 `OcrTask`。前端通过 `ocr_status` 字段感知进度，识别完成后用户可确认/修正再触发 AI 分析。开发模式（API Key 以 `placeholder` 开头）跳过真实 API，返回 mock 文字，让整条链路可在无账号时完整测试。

**Tech Stack:** Python 3.12 · FastAPI BackgroundTasks · `alibabacloud-ocr-api20210707` · `tencentcloud-sdk-python-ocr` · `asyncio.to_thread` (同步 SDK 异步包装) · OpenAI SDK (DeepSeek) · Alembic · uni-app Vue3

---

## 关键约束

- **API Key 占位符模式**：`settings.aliyun_ocr_access_key_id.startswith("placeholder")` → dev mock（与 COS 的 `_is_cos_dev_mode()` 模式一致）
- **SDK 均为同步**：阿里云 + 腾讯云 OCR SDK 是同步 HTTP 客户端，需用 `asyncio.to_thread()` 包装
- **不做版面分析**：MVP 跳过 PaddleLayout 分区，直接全图送两路 OCR，由 DeepSeek 融合
- **幂等触发**：`ocr_status == "completed"` 时不重复触发；用户可手动覆盖文字
- **错题分析前置条件**：`POST /{id}/analyze` 已有 OCR 文字时直接分析；若 `ocr_status != "completed"` 则返回 400 提示先等待 OCR

---

## 文件结构

```
新建文件：
  backend/app/services/ocr_service.py      # 双引擎 OCR + dev mock
  backend/app/schemas/ocr.py               # OcrStatusOut Pydantic schema
  backend/app/api/v1/ocr.py               # OCR API endpoints
  backend/alembic/versions/0003_add_ocr_status_to_wrong_questions.py

修改文件：
  backend/app/core/config.py               # 追加 OCR Key 字段
  backend/pyproject.toml                   # 追加两个 OCR SDK 依赖
  backend/.env.example                     # 追加 OCR key 示例
  deploy/.env.production.example           # 追加 OCR key 示例
  backend/app/models/d3_wrong_questions.py # WrongQuestion 追加 ocr_status 列
  backend/app/schemas/wrong_questions.py   # WrongQuestionOut 追加 ocr_status
  backend/app/api/v1/wrong_questions.py    # create 后触发 OCR BackgroundTask
  backend/app/api/v1/router.py             # 注册 ocr router
  frontend/miniprogram/src/types/api.ts    # 追加 OcrStatusOut 类型
  frontend/miniprogram/src/api/wrongQuestions.ts  # 追加 getOcrStatus, confirmOcrText
  frontend/miniprogram/src/pages/wrong-questions/detail.vue  # OCR 状态条 + 确认表单
```

---

## Task 0: 依赖 + Config + Alembic 迁移 0003

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `deploy/.env.production.example`
- Modify: `backend/app/models/d3_wrong_questions.py`
- Create: `backend/alembic/versions/0003_add_ocr_status_to_wrong_questions.py`

- [ ] **Step 1: 追加 OCR SDK 依赖到 pyproject.toml**

在 `backend/pyproject.toml` 的 `dependencies` 列表里，在 `"openai>=1.0.0",` 之后追加：

```toml
    "alibabacloud-ocr-api20210707>=1.0.0",
    "tencentcloud-sdk-python-ocr>=3.0.0",
```

最终 dependencies 段：
```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "alembic>=1.14.0",
    "psycopg[binary]>=3.1.0",
    "pydantic-settings>=2.3.0",
    "python-dotenv>=1.0.1",
    "python-jose[cryptography]>=3.3.0",
    "httpx>=0.27.0",
    "openai>=1.0.0",
    "alibabacloud-ocr-api20210707>=1.0.0",
    "tencentcloud-sdk-python-ocr>=3.0.0",
    "cos-python-sdk-v5>=1.9.30",
]
```

- [ ] **Step 2: 追加 OCR 配置字段到 config.py**

在 `backend/app/core/config.py` 的 `cos_base_url` 字段之后追加以下内容：

```python
    # 阿里云 OCR（印刷体识别）
    # 在 https://ram.console.aliyun.com 创建 RAM 子账号并授予 OCR 权限
    aliyun_ocr_access_key_id: str = "placeholder_aliyun_ak_id"
    aliyun_ocr_access_key_secret: str = "placeholder_aliyun_ak_secret"

    # 腾讯云 OCR（手写体识别）
    # 使用与 COS 相同的子账号即可（需开通 OCR 服务权限）
    tencent_ocr_secret_id: str = "placeholder_tencent_ocr_sid"
    tencent_ocr_secret_key: str = "placeholder_tencent_ocr_skey"
```

- [ ] **Step 3: 追加 OCR Keys 到 .env.example**

在 `backend/.env.example` 末尾追加：

```bash
# 阿里云 OCR（印刷体识别，读光高精度）
# 控制台：https://ocr.console.aliyun.com
ALIYUN_OCR_ACCESS_KEY_ID=your-aliyun-access-key-id
ALIYUN_OCR_ACCESS_KEY_SECRET=your-aliyun-access-key-secret

# 腾讯云 OCR（手写体识别）
# 控制台：https://console.cloud.tencent.com/ocr
TENCENT_OCR_SECRET_ID=your-tencent-secret-id
TENCENT_OCR_SECRET_KEY=your-tencent-secret-key
```

- [ ] **Step 4: 追加 OCR Keys 到 deploy/.env.production.example**

在 `deploy/.env.production.example` 的 `# ── DeepSeek` 块之后追加：

```bash
# ── 阿里云 OCR（印刷体）─────────────────────────────────────────────────────
ALIYUN_OCR_ACCESS_KEY_ID=AKID_YOUR_ALIYUN_ACCESS_KEY
ALIYUN_OCR_ACCESS_KEY_SECRET=YOUR_ALIYUN_ACCESS_KEY_SECRET

# ── 腾讯云 OCR（手写体）─────────────────────────────────────────────────────
TENCENT_OCR_SECRET_ID=YOUR_TENCENT_SECRET_ID
TENCENT_OCR_SECRET_KEY=YOUR_TENCENT_SECRET_KEY
```

- [ ] **Step 5: 追加 ocr_status 字段到 WrongQuestion 模型**

在 `backend/app/models/d3_wrong_questions.py` 的 `WrongQuestion` 类中，在 `updated_at` 字段之前追加：

```python
    ocr_status = mapped_column(ocr_status_enum, nullable=True)
```

完整的 WrongQuestion 末尾应如下（在 `updated_at` 之前插入）：

```python
    ocr_status = mapped_column(ocr_status_enum, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
```

- [ ] **Step 6: 创建 Alembic 迁移文件**

创建 `backend/alembic/versions/0003_add_ocr_status_to_wrong_questions.py`：

```python
"""add ocr_status to wrong_questions

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-27
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ocr_status_enum already exists from initial migration (used by ocr_tasks)
    op.add_column(
        "wrong_questions",
        sa.Column(
            "ocr_status",
            sa.Enum(
                "pending", "processing", "completed", "failed",
                name="ocr_status",
                create_type=False,   # enum type already exists
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("wrong_questions", "ocr_status")
```

- [ ] **Step 7: 运行迁移验证**

```bash
cd /path/to/engGramer/backend
alembic upgrade head
```

期望输出：`Running upgrade 0002 -> 0003, add ocr_status to wrong_questions`（需连接数据库）。若无数据库连接，跳过此步，记录待上线时执行。

- [ ] **Step 8: 提交**

```bash
git add backend/pyproject.toml backend/app/core/config.py backend/.env.example \
        deploy/.env.production.example backend/app/models/d3_wrong_questions.py \
        backend/alembic/versions/0003_add_ocr_status_to_wrong_questions.py
git commit -m "feat(ocr): add OCR config fields, SDK deps, and ocr_status migration"
```

---

## Task 1: OCR Service（双引擎 + dev mock）

**Files:**
- Create: `backend/app/services/ocr_service.py`

- [ ] **Step 1: 创建 `backend/app/services/ocr_service.py`**

```python
"""OCR 服务：阿里云（印刷体）+ 腾讯云（手写体）双引擎识别。

Dev 模式（access_key 以 'placeholder' 开头）返回 mock 文字，无需真实 API Key。
两路 SDK 均为同步接口，用 asyncio.to_thread() 包装为异步。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import settings


# ── 常量 ──────────────────────────────────────────────────────────────────────

_ALIYUN_ENDPOINT = "ocr-api.cn-hangzhou.aliyuncs.com"
_TENCENT_REGION = "ap-guangzhou"

_MOCK_PRINTED = (
    "27. The teacher asked the students to _____ their homework on time.\n"
    "A. hand in  B. hand out  C. hand over  D. hand up\n"
    "28. She _____ in Beijing for three years before she moved to Shanghai.\n"
    "A. lived  B. had lived  C. has lived  D. lives"
)
_MOCK_HANDWRITTEN = "27. B\n28. B"


# ── 返回结构 ──────────────────────────────────────────────────────────────────


@dataclass
class OcrResult:
    """两路 OCR 原始识别结果。"""
    printed_text: str    # 阿里云印刷体识别结果
    handwritten_text: str  # 腾讯云手写体识别结果


# ── Dev 模式检测 ──────────────────────────────────────────────────────────────


def _is_aliyun_dev_mode() -> bool:
    return settings.aliyun_ocr_access_key_id.startswith("placeholder")


def _is_tencent_ocr_dev_mode() -> bool:
    return settings.tencent_ocr_secret_id.startswith("placeholder")


# ── 阿里云 OCR（印刷体，同步包装）────────────────────────────────────────────


def _aliyun_recognize_sync(image_url: str) -> str:
    """调用阿里云 OCR 通用文字识别（同步）。"""
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707 import models as ocr_models
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=settings.aliyun_ocr_access_key_id,
        access_key_secret=settings.aliyun_ocr_access_key_secret,
        endpoint=_ALIYUN_ENDPOINT,
    )
    client = Client(config)
    request = ocr_models.RecognizeGeneralRequest(url=image_url)
    response = client.recognize_general(request)
    # response.body.data 为识别到的文字字符串
    return response.body.data or ""


async def _aliyun_recognize(image_url: str) -> str:
    """异步包装：阿里云印刷体 OCR。"""
    return await asyncio.to_thread(_aliyun_recognize_sync, image_url)


# ── 腾讯云 OCR（手写体，同步包装）────────────────────────────────────────────


def _tencent_handwriting_sync(image_url: str) -> str:
    """调用腾讯云手写识别 OCR（同步）。"""
    from tencentcloud.common import credential
    from tencentcloud.ocr.v20181119 import ocr_client, models

    cred = credential.Credential(
        settings.tencent_ocr_secret_id,
        settings.tencent_ocr_secret_key,
    )
    client = ocr_client.OcrClient(cred, _TENCENT_REGION)
    req = models.GeneralHandwritingOCRRequest()
    req.ImageUrl = image_url
    resp = client.GeneralHandwritingOCR(req)
    # TextDetections 是 list[TextDetection]，每项有 DetectedText
    if not resp.TextDetections:
        return ""
    return "\n".join(item.DetectedText for item in resp.TextDetections)


async def _tencent_handwriting(image_url: str) -> str:
    """异步包装：腾讯云手写体 OCR。"""
    return await asyncio.to_thread(_tencent_handwriting_sync, image_url)


# ── 公开接口 ──────────────────────────────────────────────────────────────────


async def run_ocr(image_url: str) -> OcrResult:
    """并行执行两路 OCR，返回 OcrResult。

    Dev 模式：跳过真实 API，返回 mock 文字（用于本地测试）。
    Prod 模式：两路并行 asyncio.gather()，节省等待时间。
    """
    if _is_aliyun_dev_mode() and _is_tencent_ocr_dev_mode():
        # 两路均为 placeholder → 完整 dev mock
        return OcrResult(
            printed_text=_MOCK_PRINTED,
            handwritten_text=_MOCK_HANDWRITTEN,
        )

    # 至少一路为真实 API
    printed_coro = (
        asyncio.sleep(0) if _is_aliyun_dev_mode()
        else _aliyun_recognize(image_url)
    )
    handwritten_coro = (
        asyncio.sleep(0) if _is_tencent_ocr_dev_mode()
        else _tencent_handwriting(image_url)
    )

    printed_result, handwritten_result = await asyncio.gather(
        printed_coro, handwritten_coro, return_exceptions=True
    )

    printed_text = (
        _MOCK_PRINTED if _is_aliyun_dev_mode()
        else (printed_result if isinstance(printed_result, str) else "")
    )
    handwritten_text = (
        _MOCK_HANDWRITTEN if _is_tencent_ocr_dev_mode()
        else (handwritten_result if isinstance(handwritten_result, str) else "")
    )

    return OcrResult(
        printed_text=printed_text,
        handwritten_text=handwritten_text,
    )
```

- [ ] **Step 2: 验证语法**

```bash
cd backend
python -c "from app.services.ocr_service import run_ocr, OcrResult; print('import OK')"
```

期望：`import OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/ocr_service.py
git commit -m "feat(ocr): add dual-engine OCR service with dev mock"
```

---

## Task 2: OCR 解析 Service（DeepSeek 结构化提取）

**Files:**
- Create: `backend/app/services/ocr_parser_service.py`

- [ ] **Step 1: 创建 `backend/app/services/ocr_parser_service.py`**

```python
"""OCR 结果解析：将两路 OCR 原始文字送入 DeepSeek，提取结构化字段。

输入：印刷体文字 + 手写体文字
输出：question_text / student_answer / correct_answer / question_type
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.ocr_service import OcrResult


@dataclass
class ParsedQuestion:
    """DeepSeek 从 OCR 文字中提取的结构化字段。"""
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None  # 单选|完型|阅读|作文|其他


_SYSTEM_PROMPT = (
    "你是一个专业的英语教育 OCR 后处理助手。"
    "你会收到从英语试卷图片中识别到的原始文字（印刷体 + 手写体），"
    "请提取结构化信息并严格按 JSON 格式输出，不要有任何其他文字。"
)

_USER_PROMPT_TEMPLATE = """以下是从英语试卷图片中识别到的文字：

【印刷体识别（题目印刷文字）】
{printed_text}

【手写体识别（学生作答内容）】
{handwritten_text}

请从以上文字中提取结构化信息，返回纯 JSON 格式（不要任何 markdown 代码块或额外文字）：
{{
  "question_text": "题目内容（印刷体部分，包含题干和选项，不含学生作答）",
  "student_answer": "学生手写的答案（从手写体识别中提取，若无法识别则 null）",
  "correct_answer": "正确答案（若题目中有标注或可推断则填写，否则 null）",
  "question_type": "单选|完型|阅读|作文|其他"
}}

若无法判断某字段，设为 null。"""


async def parse_ocr_result(ocr_result: OcrResult) -> ParsedQuestion:
    """将 OCR 原始文字送入 DeepSeek，返回结构化 ParsedQuestion。

    异常处理：
    - API 错误 → AppError(502, "OCR解析服务暂时不可用")
    - JSON 解析失败 → AppError(500, "OCR解析返回格式异常")
    """
    prompt = _USER_PROMPT_TEMPLATE.format(
        printed_text=ocr_result.printed_text or "(无印刷体识别结果)",
        handwritten_text=ocr_result.handwritten_text or "(无手写体识别结果)",
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"OCR解析服务暂时不可用（{exc}）") from exc

    raw_text = (response.choices[0].message.content or "").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="OCR解析返回格式异常") from exc

    valid_types = {"单选", "完型", "阅读", "作文", "其他"}
    question_type = data.get("question_type")
    if question_type not in valid_types:
        question_type = "其他"

    return ParsedQuestion(
        question_text=data.get("question_text"),
        student_answer=data.get("student_answer"),
        correct_answer=data.get("correct_answer"),
        question_type=question_type,
    )
```

- [ ] **Step 2: 验证语法**

```bash
cd backend
python -c "from app.services.ocr_parser_service import parse_ocr_result, ParsedQuestion; print('import OK')"
```

期望：`import OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/ocr_parser_service.py
git commit -m "feat(ocr): add DeepSeek OCR result parser service"
```

---

## Task 3: OCR Schemas + API Endpoints

**Files:**
- Create: `backend/app/schemas/ocr.py`
- Create: `backend/app/api/v1/ocr.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/schemas/wrong_questions.py`

- [ ] **Step 1: 创建 `backend/app/schemas/ocr.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OcrStatusOut(BaseModel):
    """OCR 任务状态（供前端轮询）。"""
    wrong_question_id: uuid.UUID
    ocr_status: str | None           # pending / processing / completed / failed / None
    printed_text: str | None         # 阿里云原始识别结果
    handwritten_text: str | None     # 腾讯云原始识别结果
    error_message: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ConfirmOcrTextRequest(BaseModel):
    """PATCH /wrong-questions/{id}/text 请求体：手动确认/修正 OCR 文字。"""
    question_text: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    question_type: str | None = None
```

- [ ] **Step 2: 更新 `backend/app/schemas/wrong_questions.py`，在 WrongQuestionOut 中追加 ocr_status**

在 `WrongQuestionOut` 类的 `updated_at: datetime` 字段之后，追加：

```python
    ocr_status: str | None = None
```

完整的 `WrongQuestionOut` 应如下：
```python
class WrongQuestionOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    source_image_url: str
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None
    difficulty: int | None
    tags: list[str] | None
    is_mastered: bool
    mastered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ocr_status: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: 创建 `backend/app/api/v1/ocr.py`**

```python
"""OCR 相关 API。

POST  /wrong-questions/{id}/ocr        触发 OCR（幂等，completed 不重复触发）
GET   /wrong-questions/{id}/ocr        查询最新 OCR 任务状态
PATCH /wrong-questions/{id}/text       手动确认/覆盖 OCR 识别文字
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d3_wrong_questions import OcrTask, WrongQuestion
from app.schemas.base import BaseResponse, make_ok
from app.schemas.ocr import ConfirmOcrTextRequest, OcrStatusOut
from app.schemas.wrong_questions import WrongQuestionOut
from app.services import wrong_question_service

router = APIRouter(prefix="/wrong-questions", tags=["ocr"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


async def _run_ocr_pipeline(wq_id: uuid.UUID) -> None:
    """后台任务：执行 OCR + DeepSeek 解析，写回 WrongQuestion。"""
    from app.core.database import async_session_factory
    from app.services.ocr_service import run_ocr
    from app.services.ocr_parser_service import parse_ocr_result

    async with async_session_factory() as db:
        wq: WrongQuestion | None = await db.get(WrongQuestion, wq_id)
        if wq is None:
            return

        # 创建 OcrTask 记录，状态设为 processing
        ocr_task = OcrTask(
            wrong_question_id=wq_id,
            status="processing",
            provider="aliyun_print",  # 主引擎标识
        )
        db.add(ocr_task)
        wq.ocr_status = "processing"  # type: ignore[assignment]
        await db.commit()

        try:
            ocr_result = await run_ocr(wq.source_image_url)
            parsed = await parse_ocr_result(ocr_result)

            # 写回结构化字段
            wq.question_text = parsed.question_text
            wq.student_answer = parsed.student_answer
            wq.correct_answer = parsed.correct_answer
            if parsed.question_type and wq.question_type is None:
                wq.question_type = parsed.question_type  # type: ignore[assignment]
            wq.ocr_status = "completed"  # type: ignore[assignment]

            # 更新 OcrTask 记录
            import json
            from datetime import datetime, timezone
            ocr_task.status = "completed"  # type: ignore[assignment]
            ocr_task.raw_result = {  # type: ignore[assignment]
                "printed_text": ocr_result.printed_text,
                "handwritten_text": ocr_result.handwritten_text,
            }
            ocr_task.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            wq.ocr_status = "failed"  # type: ignore[assignment]
            ocr_task.status = "failed"  # type: ignore[assignment]
            ocr_task.error_message = str(exc)

        await db.commit()


@router.post("/{wq_id}/ocr", response_model=BaseResponse[WrongQuestionOut])
async def trigger_ocr(
    wq_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """触发 OCR 识别（幂等：completed 状态不重新触发）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    if wq.ocr_status == "completed":
        return make_ok(WrongQuestionOut.model_validate(wq))
    if wq.ocr_status == "processing":
        raise AppError(code=409, message="OCR 识别正在进行中，请稍后查询状态")

    # 标记 pending
    wq.ocr_status = "pending"  # type: ignore[assignment]
    await db.commit()
    await db.refresh(wq)

    # 异步后台执行
    background_tasks.add_task(_run_ocr_pipeline, wq_id)

    return make_ok(WrongQuestionOut.model_validate(wq))


@router.get("/{wq_id}/ocr", response_model=BaseResponse[OcrStatusOut])
async def get_ocr_status(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查询最新 OCR 任务状态。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    # 查最新 OcrTask
    result = await db.execute(
        select(OcrTask)
        .where(OcrTask.wrong_question_id == wq_id)
        .order_by(OcrTask.created_at.desc())
        .limit(1)
    )
    task = result.scalar_one_or_none()

    return make_ok(
        OcrStatusOut(
            wrong_question_id=wq_id,
            ocr_status=wq.ocr_status,
            printed_text=task.raw_result.get("printed_text") if task and task.raw_result else None,
            handwritten_text=task.raw_result.get("handwritten_text") if task and task.raw_result else None,
            error_message=task.error_message if task else None,
            updated_at=task.updated_at if task else None,
        )
    )


@router.patch("/{wq_id}/text", response_model=BaseResponse[WrongQuestionOut])
async def confirm_ocr_text(
    wq_id: uuid.UUID,
    body: ConfirmOcrTextRequest,
    db: DbDep,
    current_user: UserDep,
):
    """手动确认/覆盖 OCR 识别结果（用户可修正识别错误）。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.get_wrong_question(
        db, wq_id=wq_id, student_id=current_user.id
    )
    if wq is None:
        raise AppError(code=404, message="错题不存在或无权访问")

    if body.question_text is not None:
        wq.question_text = body.question_text
    if body.student_answer is not None:
        wq.student_answer = body.student_answer
    if body.correct_answer is not None:
        wq.correct_answer = body.correct_answer
    if body.question_type is not None:
        wq.question_type = body.question_type  # type: ignore[assignment]

    # 手动修正后强制标记为 completed
    wq.ocr_status = "completed"  # type: ignore[assignment]

    await db.commit()
    await db.refresh(wq)
    return make_ok(WrongQuestionOut.model_validate(wq))
```

- [ ] **Step 4: 在 router.py 注册 ocr router**

读取 `backend/app/api/v1/router.py`，追加 ocr_router：

```python
from app.api.v1.ocr import router as ocr_router
# ...
v1_router.include_router(ocr_router)
```

- [ ] **Step 5: 验证语法**

```bash
cd backend
python -c "from app.api.v1.ocr import router; print('import OK')"
```

期望：`import OK`

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/ocr.py backend/app/schemas/wrong_questions.py \
        backend/app/api/v1/ocr.py backend/app/api/v1/router.py
git commit -m "feat(ocr): add OCR schemas, API endpoints (trigger/status/confirm)"
```

---

## Task 4: 集成 — 上传后自动触发 OCR + AI 分析前置检查

**Files:**
- Modify: `backend/app/api/v1/wrong_questions.py`
- Modify: `backend/app/core/database.py` (若 async_session_factory 未导出则需添加)

- [ ] **Step 1: 检查 database.py 是否导出 async_session_factory**

```bash
grep "async_session_factory\|sessionmaker\|AsyncSession" backend/app/core/database.py | head -10
```

若没有 `async_session_factory`，在 `backend/app/core/database.py` 末尾追加：

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

如果文件中已有类似代码，复用已有的 session maker 名称，并在 `ocr.py` 中调整导入路径。

- [ ] **Step 2: 修改 `POST /wrong-questions/`，上传后自动触发 OCR**

在 `backend/app/api/v1/wrong_questions.py` 的 `create_wrong_question` endpoint 中：
1. 在函数参数中增加 `background_tasks: BackgroundTasks`
2. 在 `await db.commit()` 和 `await db.refresh(wq)` 之后追加 OCR 触发逻辑

修改后的 endpoint：

```python
@router.post("/", response_model=BaseResponse[WrongQuestionOut])
async def create_wrong_question(
    body: WrongQuestionCreate,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """提交新错题，自动触发后台 OCR 识别。"""
    await get_rls_db(db, str(current_user.id))
    wq = await wrong_question_service.create_wrong_question(
        db, student_id=current_user.id, data=body
    )
    # 初始化 ocr_status = pending（迁移后模型已有此字段）
    wq.ocr_status = "pending"  # type: ignore[assignment]
    await db.commit()
    await db.refresh(wq)

    # 后台异步触发 OCR（不阻塞响应）
    from app.api.v1.ocr import _run_ocr_pipeline
    background_tasks.add_task(_run_ocr_pipeline, wq.id)

    return make_ok(WrongQuestionOut.model_validate(wq))
```

在文件顶部 import 中追加：
```python
from fastapi import APIRouter, BackgroundTasks, Depends, Query
```

- [ ] **Step 3: 修改 `POST /{wq_id}/analyze`，OCR 未完成时拒绝**

在 `wrong_questions.py` 的 `analyze_wrong_question` endpoint 中，在 `wq is None` 检查之后追加：

```python
    # OCR 尚未完成时拒绝触发 AI 分析
    if wq.ocr_status not in ("completed", None):
        raise AppError(
            code=400,
            message=f"OCR 识别尚未完成（当前状态：{wq.ocr_status}），请稍后再试",
        )
```

注意：`ocr_status is None` 的情况对应旧数据（迁移前的记录），允许直接分析（向下兼容）。

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/v1/wrong_questions.py backend/app/core/database.py
git commit -m "feat(ocr): auto-trigger OCR on wrong question create, block AI before OCR done"
```

---

## Task 5: 前端 — OCR 状态条 + 确认/编辑表单

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/api/wrongQuestions.ts`
- Modify: `frontend/miniprogram/src/pages/wrong-questions/detail.vue`

- [ ] **Step 1: 追加类型到 `frontend/miniprogram/src/types/api.ts`**

在文件末尾追加：

```typescript
/** OCR 任务状态 — GET /wrong-questions/{id}/ocr */
export interface OcrStatusOut {
  wrong_question_id: string
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed' | null
  printed_text: string | null
  handwritten_text: string | null
  error_message: string | null
  updated_at: string | null
}

/** 手动确认 OCR 文字 — PATCH /wrong-questions/{id}/text */
export interface ConfirmOcrTextRequest {
  question_text?: string | null
  student_answer?: string | null
  correct_answer?: string | null
  question_type?: string | null
}
```

同时在 `WrongQuestionOut` 接口中追加 `ocr_status` 字段：
```typescript
export interface WrongQuestionOut {
  // ... 已有字段 ...
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed' | null
}
```

- [ ] **Step 2: 追加 API 函数到 `frontend/miniprogram/src/api/wrongQuestions.ts`**

在文件末尾追加：

```typescript
/** 触发 OCR 识别 */
export function triggerOcr(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/ocr`, {
    method: 'POST',
  })
}

/** 查询 OCR 任务状态 */
export function getOcrStatus(id: string): Promise<OcrStatusOut> {
  return request<OcrStatusOut>(`/api/v1/wrong-questions/${id}/ocr`)
}

/** 手动确认/覆盖 OCR 识别结果 */
export function confirmOcrText(
  id: string,
  data: ConfirmOcrTextRequest,
): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/text`, {
    method: 'PATCH',
    data,
  })
}
```

在文件顶部 import 中追加 `OcrStatusOut, ConfirmOcrTextRequest`：
```typescript
import type { AiAnalysisOut, ConfirmOcrTextRequest, OcrStatusOut, WrongQuestionOut } from '@/types/api'
```

- [ ] **Step 3: 更新 `detail.vue`，添加 OCR 状态条 + 确认/编辑表单**

在现有 `<template>` 中，在「元信息卡」之前插入 OCR 状态卡：

```html
<!-- OCR 识别状态卡 -->
<view class="card" v-if="wq">
  <!-- 状态条 -->
  <view class="ocr-status-bar" :class="ocrStatusClass">
    <text class="ocr-status-icon">{{ ocrStatusIcon }}</text>
    <text class="ocr-status-text">{{ ocrStatusText }}</text>
    <button
      v-if="wq.ocr_status === 'failed' || wq.ocr_status === null"
      class="btn-ocr-retry"
      @tap="onTriggerOcr"
    >重新识别</button>
  </view>

  <!-- OCR 结果确认/编辑表单（completed 状态显示） -->
  <view v-if="wq.ocr_status === 'completed'" class="ocr-form">
    <view class="card-title" style="margin-top: 20rpx">识别内容确认</view>
    <view class="ocr-field">
      <text class="label">题目内容</text>
      <textarea
        class="ocr-textarea"
        :value="editQuestion"
        @input="editQuestion = $event.detail.value"
        placeholder="AI 识别的题目文字"
        auto-height
      />
    </view>
    <view class="ocr-field">
      <text class="label">你的作答</text>
      <input
        class="ocr-input"
        :value="editAnswer"
        @input="editAnswer = $event.detail.value"
        placeholder="识别的手写答案"
      />
    </view>
    <view class="ocr-field">
      <text class="label">正确答案</text>
      <input
        class="ocr-input"
        :value="editCorrect"
        @input="editCorrect = $event.detail.value"
        placeholder="正确答案（可选）"
      />
    </view>
    <button
      class="btn-confirm"
      :disabled="confirming"
      @tap="onConfirmOcr"
    >
      {{ confirming ? '保存中…' : '确认内容' }}
    </button>
  </view>
</view>
```

在 `<script setup lang="ts">` 中追加：

```typescript
import {
  analyzeWrongQuestion,
  confirmOcrText,
  getWrongQuestion,
  listAnalyses,
  markMastered,
  triggerOcr,
} from '@/api/wrongQuestions'
import type { AiAnalysisOut, ConfirmOcrTextRequest, WrongQuestionOut } from '@/types/api'

// OCR 编辑状态
const editQuestion = ref('')
const editAnswer = ref('')
const editCorrect = ref('')
const confirming = ref(false)
let ocrPollTimer: ReturnType<typeof setInterval> | null = null

// OCR 状态展示
const ocrStatusClass = computed(() => {
  const map: Record<string, string> = {
    pending: 'ocr-pending',
    processing: 'ocr-processing',
    completed: 'ocr-completed',
    failed: 'ocr-failed',
  }
  return map[wq.value?.ocr_status ?? ''] ?? 'ocr-unknown'
})

const ocrStatusIcon = computed(() => {
  const map: Record<string, string> = {
    pending: '⏳',
    processing: '🔄',
    completed: '✅',
    failed: '❌',
  }
  return map[wq.value?.ocr_status ?? ''] ?? '❓'
})

const ocrStatusText = computed(() => {
  const map: Record<string, string> = {
    pending: 'OCR 识别等待中…',
    processing: '正在识别题目文字（约 5-15 秒）…',
    completed: 'OCR 识别完成，请确认内容',
    failed: 'OCR 识别失败',
  }
  return map[wq.value?.ocr_status ?? ''] ?? '未触发 OCR'
})

// 当 OCR 处于 pending/processing 时，每 3 秒轮询一次
function startOcrPolling() {
  if (ocrPollTimer) return
  ocrPollTimer = setInterval(async () => {
    if (!wq.value) return
    const status = wq.value.ocr_status
    if (status !== 'pending' && status !== 'processing') {
      stopOcrPolling()
      return
    }
    try {
      wq.value = await getWrongQuestion(wqId)
      if (wq.value.ocr_status === 'completed') {
        // 预填编辑框
        editQuestion.value = wq.value.question_text ?? ''
        editAnswer.value = wq.value.student_answer ?? ''
        editCorrect.value = wq.value.correct_answer ?? ''
        stopOcrPolling()
      }
    } catch (_) { /* 静默忽略轮询错误 */ }
  }, 3000)
}

function stopOcrPolling() {
  if (ocrPollTimer) {
    clearInterval(ocrPollTimer)
    ocrPollTimer = null
  }
}

async function onTriggerOcr() {
  if (!wq.value) return
  try {
    wq.value = await triggerOcr(wqId)
    startOcrPolling()
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  }
}

async function onConfirmOcr() {
  if (!wq.value) return
  confirming.value = true
  try {
    const data: ConfirmOcrTextRequest = {
      question_text: editQuestion.value || null,
      student_answer: editAnswer.value || null,
      correct_answer: editCorrect.value || null,
    }
    wq.value = await confirmOcrText(wqId, data)
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    confirming.value = false
  }
}

// 在 onMounted 中加入 OCR 预填 + 自动轮询
// 在现有 onMounted 的 try 块末尾追加：
//   if (wq.value?.ocr_status === 'completed') {
//     editQuestion.value = wq.value.question_text ?? ''
//     editAnswer.value = wq.value.student_answer ?? ''
//     editCorrect.value = wq.value.correct_answer ?? ''
//   } else if (wq.value?.ocr_status === 'pending' || wq.value?.ocr_status === 'processing') {
//     startOcrPolling()
//   }

// onUnmounted 清除定时器
import { onUnmounted } from 'vue'
onUnmounted(() => stopOcrPolling())
```

在 `<style scoped>` 末尾追加样式：

```css
/* OCR 状态条 */
.ocr-status-bar {
  display: flex;
  align-items: center;
  padding: 16rpx;
  border-radius: 10rpx;
  gap: 12rpx;
}
.ocr-pending, .ocr-unknown { background: #f5f5f5; }
.ocr-processing { background: #e6f4ff; }
.ocr-completed { background: #f0fff4; }
.ocr-failed { background: #fff0f0; }
.ocr-status-icon { font-size: 32rpx; }
.ocr-status-text { flex: 1; font-size: 26rpx; color: #555; }
.btn-ocr-retry {
  font-size: 24rpx; height: 56rpx; line-height: 56rpx;
  background: #1677ff; color: #fff; border-radius: 8rpx; padding: 0 20rpx;
}

/* OCR 编辑表单 */
.ocr-form { margin-top: 16rpx; }
.ocr-field { margin-bottom: 20rpx; }
.ocr-textarea {
  width: 100%; min-height: 120rpx; background: #f9f9f9;
  border-radius: 8rpx; padding: 16rpx; font-size: 26rpx; color: #333;
  box-sizing: border-box;
}
.ocr-input {
  width: 100%; height: 72rpx; background: #f9f9f9;
  border-radius: 8rpx; padding: 0 16rpx; font-size: 26rpx; color: #333;
}
.btn-confirm {
  background: #52c41a; color: #fff; border-radius: 10rpx;
  font-size: 28rpx; height: 80rpx; line-height: 80rpx; width: 100%;
}
.btn-confirm[disabled] { opacity: 0.5; }
```

- [ ] **Step 4: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/wrongQuestions.ts \
        frontend/miniprogram/src/pages/wrong-questions/detail.vue
git commit -m "feat(ocr): add OCR status UI, confirmation form, and polling in detail page"
```

---

## Task 6: 集成测试 + D-068 归档

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: Dev 模式端到端验证**

```bash
# 启动后端（确保 .env 中 OCR keys 为 placeholder）
cd backend && uvicorn app.main:app --reload

# 1. 登录获取 access_token
curl -s -X POST http://localhost:8000/api/v1/auth/wx-login \
  -H "Content-Type: application/json" \
  -d '{"code":"test"}' | python3 -m json.tool

# 2. 创建错题（用 mock COS URL）
ACCESS_TOKEN=<your_token>
curl -s -X POST http://localhost:8000/api/v1/wrong-questions/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_image_url":"https://mock-cos.dev/test.jpg"}' | python3 -m json.tool
# 期望：ocr_status = "pending"，且后台立即开始 OCR

# 3. 等 2-3 秒，查询 OCR 状态
WQ_ID=<id_from_above>
curl -s http://localhost:8000/api/v1/wrong-questions/$WQ_ID/ocr \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool
# 期望：ocr_status = "completed"，printed_text/handwritten_text 为 mock 文字

# 4. 确认 OCR 文字
curl -s -X PATCH http://localhost:8000/api/v1/wrong-questions/$WQ_ID/text \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question_text":"27. hand in ...", "student_answer":"B"}' | python3 -m json.tool
# 期望：question_text/student_answer 已更新

# 5. 触发 AI 分析（现在有真实 question_text 了）
curl -s -X POST http://localhost:8000/api/v1/wrong-questions/$WQ_ID/analyze \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool
# 期望：diagnosis/suggestions 基于真实题目内容生成
```

- [ ] **Step 2: 验证 AI 分析前置检查**

```bash
# 创建一个新错题，在 OCR 完成前立即尝试 AI 分析
WQ_ID2=<new_wq_id>
curl -s -X POST http://localhost:8000/api/v1/wrong-questions/$WQ_ID2/analyze \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool
# 期望：{"code": 400, "message": "OCR 识别尚未完成（当前状态：pending）"}
```

- [ ] **Step 3: 前端 build 验证**

```bash
cd frontend/miniprogram
pnpm build:mp-weixin 2>&1 | grep -E "error|ERROR|warning|WARNING" | head -20
```

期望：无 TypeScript error，只有可能的 warning。

- [ ] **Step 4: 追加 D-068 到 docs/决策归档.md**

在 D-067 之前插入：

```markdown
## D-068｜Plan G OCR 管道：阿里云（印刷体）+ 腾讯云（手写体）→ DeepSeek 解析

**日期：** 2026-05-27
**背景：** 错题提交后 question_text 始终为 null，AI 分析基于"(暂无文字内容)"，诊断结果无意义。需要实现 OCR 管道将图片内容结构化，喂给 AI 分析。
**结论：**
1. **双引擎 OCR：** 阿里云 RecognizeGeneral（印刷体题目）+ 腾讯云 GeneralHandwritingOCR（手写作答），两路并行 asyncio.gather()；SDK 均为同步，用 asyncio.to_thread() 包装。MVP 跳过版面分析，全图送两路引擎，由 DeepSeek 融合。
2. **Dev Mock：** aliyun_ocr_access_key_id 以 "placeholder" 开头时跳过真实 API，返回预设 mock 文字（与 COS dev mode 模式一致）。
3. **DeepSeek 解析层：** OCR 两路原始文字 → DeepSeek deepseek-chat → 返回 {question_text, student_answer, correct_answer, question_type} JSON。
4. **异步流程：** POST /wrong-questions/ 立即返回（ocr_status=pending），后台 BackgroundTask 执行 OCR → 解析 → 写回；前端每 3 秒轮询 ocr_status。
5. **状态机：** WrongQuestion.ocr_status = null / pending / processing / completed / failed；Alembic 0003 追加该列；POST /{id}/analyze 在 ocr_status != completed 时返回 400。
6. **前端：** detail.vue 新增 OCR 状态条（颜色+图标+文字）、确认/编辑表单（可修正识别错误）、轮询 + onUnmounted 清理定时器。
7. **降级策略：** 任一引擎抛异常时 OcrResult 对应字段置空，DeepSeek 仍尝试解析可用的部分；完全失败时 ocr_status=failed，前端显示"重新识别"按钮。
**影响范围：** 新增 ocr_service.py、ocr_parser_service.py、schemas/ocr.py、api/v1/ocr.py；Alembic 0003；修改 wrong_questions.py endpoint、detail.vue；已推送 GitHub main 分支。
```

- [ ] **Step 5: 提交 + Push**

```bash
git add docs/决策归档.md
git commit -m "docs: archive D-068 — Plan G OCR pipeline"
git push origin main
```

---

## 自检清单

**Spec 覆盖：**
- ✅ 印刷体 → 阿里云 OCR（RecognizeGeneral）
- ✅ 手写体 → 腾讯云 OCR（GeneralHandwritingOCR）
- ✅ Dev mock（无账号可测试全链路）
- ✅ OCR 结果 → DeepSeek 结构化解析
- ✅ question_text / student_answer / correct_answer 写回 WrongQuestion
- ✅ 异步流程（不阻塞 POST /wrong-questions/ 响应）
- ✅ 前端状态条 + 轮询 + 手动确认/编辑
- ✅ AI 分析前置检查（OCR 未完成则 400）
- ✅ 降级：引擎失败时 ocr_status=failed + 前端重试入口

**暂不实现（V2）：**
- PaddleLayout 版面分析分区（印刷体/手写体精确分离）
- 低置信度区域高亮（需要 OCR API 返回坐标信息）
- 备选引擎自动切换（百度 OCR / Google Document AI）
- 60s 超时异步推送通知
