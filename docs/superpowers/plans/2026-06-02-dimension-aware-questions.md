# 维度感知练习题（Dimension-Aware Practice Questions）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让"听力/听写/语法/写作"四个维度的练习题与模拟考各有特色（听力=读对话/短文做理解，听写=拼写填空，语法=单选/填空/判断，写作=作文/连线），不再四个 tab 共用同一批语法题。

**Architecture:** 给 `simulated_questions` 加一个可空的 `dimension` 列（复用已存在的 `content_dimension` enum）。AI 生题改为"按维度"出题：`generate_questions` 增加 `dimension` 参数，按维度选用不同 prompt + 不同 dev-mock 题集；`persist_questions` 把维度写入行；读取接口 `list_questions_by_kp` 支持按维度过滤；API `practice-questions` 增加 `dimension` query 参数；前端 KP 详情页把当前 tab 的维度透传给练习/模拟考页面。`dimension` 全程可空且默认 `"grammar"`，保证旧数据、旧测试、旧 seed 行为不变（向后兼容）。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL + Alembic；DeepSeek（OpenAI 兼容）AI 生题；前端 uni-app（Vue 3 setup）小程序。

**关键约束（贯穿全程）：**
- **CWD 是 `backend/`，测试在仓库根 `tests/`（用 `../tests` 引用）。** 跑测试：
  `cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/... -v`
- Alembic 当前 head = `0013`，DB 当前 revision = `0013`。新迁移编号 `0014`，`down_revision="0013"`。
- `content_dimension` enum **已存在于 DB**（迁移 0007 建的），迁移 0014 **绝不可重建该类型**，必须 `create_type=False`。
- **DeepSeek 真实调用会花钱。** Task 0-7 全部用 dev-mock（`deepseek_api_key` 以 `sk-placeholder` 开头时触发），不花钱。Task 8（真实重灌题库）默认**只用 dev-mock 验证流程**；任何真实 DeepSeek spend 必须先向用户确认预算后再跑（标准约束）。
- 回答用户用中文。

**设计取舍（已确认 / 已决定）：**
- 用户已选方案 A「维度感知出题（听力/听写先用文本近似）」。真听力/听写需要音频/TTS（M2.5，已推迟），所以听力=文本呈现对话/短文，听写=给中文/语境拼写英文单词。
- `dimension` 不加进 `AIGeneratedQuestion` schema：维度是"调用方"概念（调用方知道在为哪个维度出题），不是 AI 的输出。作为函数参数贯穿 `generate_questions` / `persist_questions`，更 DRY，也不要求 AI 回显维度。
- `SimQuestionOut` 不暴露 `dimension`：前端按 `question_type` 渲染，不需要维度字段。保持最小改动。
- 维度过滤为**严格过滤**（给了 dimension 就只返回该维度的题）。某维度暂无题时前端已有"该知识点暂无题目"兜底。旧的 `dimension IS NULL` 题不会出现在任何维度 tab，需 Task 8 重灌后才有维度题——这是可接受的、诚实的过渡态。

---

## File Structure

**后端（backend/，CWD）：**
- Create: `alembic/versions/0014_sim_question_dimension.py` — 给 `simulated_questions` 加 `dimension` 列。
- Modify: `app/models/d12_v2_exams.py` — `SimulatedQuestion` 加 `dimension` 字段（复用 d11 的 `dimension_enum`）。
- Modify: `app/services/question_ai_service.py` — 4 个维度 prompt + 维度感知 dev-mock + `generate_questions` 加 `dimension` 参数 + 修 `max_tokens=4096→8192` 和 `json.loads(strict=False)` 两个 bug。
- Modify: `app/services/question_service.py` — `persist_questions` 写 `dimension`；`list_questions_by_kp` 支持 `dimension` 过滤。
- Modify: `app/api/v1/questions.py` — `practice-questions` 端点加 `dimension` query 参数。
- Modify: `scripts/seed_questions.py` — 按维度循环生题。

**测试（tests/，仓库根）：**
- Modify: `tests/services/test_question_ai_service.py` — 加维度感知 mock 断言。
- Modify: `tests/services/test_question_service.py` — 加 persist 写维度 + list 维度过滤断言。
- Modify: `tests/api/test_questions.py` — 加 API `dimension` 参数过滤断言。

**前端（frontend/miniprogram/src/）：**
- Modify: `api/questions.ts` — `listPracticeQuestions` 加 `dimension` 参数。
- Modify: `pages/curriculum/kp-content.vue` — `goPractice`/`goExam` 透传 `dim=activeDim`。
- Modify: `pages/practice/v2-session.vue` — `onLoad` 读 `q.dim` 并透传。
- Modify: `pages/practice/v2-exam.vue` — `onLoad` 读 `q.dim` 并透传。

**文档：**
- Modify: `docs/决策归档.md` — 顶部加 D-091 条目。

---

## Task 0: 迁移 0014 + 模型加 `dimension` 列

**Files:**
- Create: `backend/alembic/versions/0014_sim_question_dimension.py`
- Modify: `backend/app/models/d12_v2_exams.py`
- Test: 用 `alembic upgrade head` + `\d simulated_questions` 验证

- [ ] **Step 1: 写迁移 0014**

Create `backend/alembic/versions/0014_sim_question_dimension.py`:

```python
"""add dimension to simulated_questions (维度感知练习题)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# 复用迁移 0007 已创建的 content_dimension 枚举，绝不重建类型
_dimension = postgresql.ENUM(
    "listening", "dictation", "grammar", "writing",
    name="content_dimension", create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "simulated_questions",
        sa.Column("dimension", _dimension, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulated_questions", "dimension")
```

- [ ] **Step 2: 运行迁移并验证列已加**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m alembic upgrade head
DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m alembic current
```
Expected: `current` 输出 `0014 (head)`。再确认列存在：
```bash
psql postgresql://postgres:dev@localhost:5432/enggramer -c "\d simulated_questions" | grep dimension
```
Expected: 看到 `dimension | content_dimension |` 一行（nullable）。

- [ ] **Step 3: 模型加 `dimension` 字段**

In `backend/app/models/d12_v2_exams.py`, 顶部 import 区（已有 `from .d6_ai_questions import ai_question_type_enum`）后面加一行复用 d11 的枚举对象：

```python
from .d11_v2_curriculum import dimension_enum
```

然后在 `class SimulatedQuestion` 里，`difficulty` 行之后、`generation_metadata` 行之前加：

```python
    dimension = mapped_column(dimension_enum, nullable=True)
```

（复用同一个 `dimension_enum` 实例，SQLAlchemy 视为同一类型，不会重复建类型。）

- [ ] **Step 4: 验证模型导入不报错**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -c "from app.models.d12_v2_exams import SimulatedQuestion; print(SimulatedQuestion.dimension)"
```
Expected: 打印一个 InstrumentedAttribute，无 ImportError、无 "type content_dimension already exists"。

- [ ] **Step 5: Commit**

```bash
cd backend && git add alembic/versions/0014_sim_question_dimension.py app/models/d12_v2_exams.py
git commit -m "feat: add dimension column to simulated_questions (维度感知练习题 migration 0014)"
```

---

## Task 1: `question_ai_service` 维度感知生题 + 修 2 个 bug

**Files:**
- Modify: `backend/app/services/question_ai_service.py`
- Test: `tests/services/test_question_ai_service.py`

**背景：** 当前 `generate_questions` 对所有维度出同一批"混合题"。要按维度出题：listening=读对话/短文做理解（文本近似），dictation=拼写填空，grammar=现有混合，writing=作文/连线。同时这个文件还残留 M3 的两个 bug（`max_tokens=4096` 会截断、`json.loads` 默认 strict 会被裸控制字符噎住），一并修掉——curriculum_ai_service 已修过同样问题。

- [ ] **Step 1: 写失败测试（维度感知 mock）**

In `tests/services/test_question_ai_service.py`, 在文件末尾追加：

```python
@pytest.mark.asyncio
async def test_listening_mock_is_comprehension_not_grammar():
    """听力维度：题型只在 单选/阅读（文本近似理解题），题干含对话/短文。"""
    qs = await generate_questions(
        kp_name="一般现在时", kp_category="grammar", kp_description="d",
        dimension="listening", count=4,
    )
    assert len(qs) == 4
    assert all(q.question_type in ("单选", "阅读") for q in qs)
    # 听力题干应含"对话/短文/听"等理解线索（mock 固定带"听力材料"）
    assert any("听" in q.stem for q in qs)
    for q in qs:
        assert q.options is not None and len(q.options) == 4
        assert q.answer in ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_dictation_mock_is_spelling_fill():
    """听写维度：题型只在 填空（拼写），无选项。"""
    qs = await generate_questions(
        kp_name="单词拼写", kp_category="vocabulary", kp_description="d",
        dimension="dictation", count=4,
    )
    assert len(qs) == 4
    assert all(q.question_type == "填空" for q in qs)
    for q in qs:
        assert q.options is None
        assert q.answer


@pytest.mark.asyncio
async def test_writing_mock_is_essay_or_match():
    """写作维度：题型只在 写作/连线。"""
    qs = await generate_questions(
        kp_name="写一段自我介绍", kp_category="writing", kp_description="d",
        dimension="writing", count=4,
    )
    assert len(qs) == 4
    assert all(q.question_type in ("写作", "连线") for q in qs)


@pytest.mark.asyncio
async def test_grammar_dimension_unchanged_default():
    """语法维度（默认）：保持原有混合题型行为，覆盖 7 类。"""
    qs = await generate_questions(
        kp_name="X", kp_category="grammar", kp_description="d",
        dimension="grammar", count=9,
    )
    types = {q.question_type for q in qs}
    assert types == {"单选", "填空", "判断", "完型", "阅读", "写作", "连线"}
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_question_ai_service.py -v
```
Expected: 4 个新测试 FAIL（`generate_questions() got an unexpected keyword argument 'dimension'`）。原有 2 个测试仍 PASS。

- [ ] **Step 3: 改 `generate_questions` 为维度感知 + 修 2 个 bug**

In `backend/app/services/question_ai_service.py`，整体替换为下面内容（保留原 `_USER_PROMPT_TEMPLATE` 作为 grammar 维度模板，新增 3 个维度模板 + 维度 dispatch + 维度感知 mock + 修 bug）：

```python
"""V2 仿真题 AI 生成 service（D-079 / M3a；D-091 维度感知）。

调 DeepSeek 为某个知识点 + 某个维度生成 N 道题。维度决定题型与 prompt：
- listening 听力：读对话/短文做理解（文本近似，真音频留待 M2.5），题型 单选/阅读
- dictation 听写：拼写填空，题型 填空
- grammar 语法：单选/填空/判断/完型/阅读/写作/连线 混合（原行为）
- writing 写作：作文 + 连线
dev mode 返回固定结构供前端/集成测试无 key 时跑通。
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.questions import AIGeneratedQuestion

_SYSTEM_PROMPT = (
    "你是中国中小学英语命题老师，按知识点和指定维度出仿真题。"
    "严格按 JSON 数组输出，不要任何 markdown 代码块或额外文字。"
)

# ─── grammar（语法，原行为）─────────────────────────────────────────────────
_GRAMMAR_PROMPT = """请为以下知识点生成 {count} 道语法仿真题。

知识点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

题型分配（{count} 道，建议比例）：
- 单选 ≥ 1 道：4 个选项，标记 A-D，answer 是单个字母
- 填空 ≥ 1 道：options 为 null，answer 可用 | 分隔多个合法答案（如 "goes|go"）
- 判断 ≥ 1 道：options 为 null，answer 是 "对" 或 "错"
- 完型 0-1 道：stem 是含 1 个空白的短文（< 80 字），4 个选项，answer 单字母
- 阅读 0-1 道：stem 是 100-150 字短文 + 一个理解问题，4 个选项，answer 单字母

每题必须含 explanation（≥ 20 字解析）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "单选", "stem": "...", "options": ["A. ...","B. ...","C. ...","D. ..."], "answer": "B", "explanation": "...", "difficulty": 2}},
  {{"question_type": "填空", "stem": "He ___ to school every day.", "options": null, "answer": "goes", "explanation": "...", "difficulty": 2}},
  {{"question_type": "判断", "stem": "...", "options": null, "answer": "错", "explanation": "...", "difficulty": 1}}
]"""

# ─── listening（听力，文本近似）──────────────────────────────────────────────
_LISTENING_PROMPT = """请为以下知识点生成 {count} 道"听力理解"仿真题（暂用文本呈现听力材料，不含音频）。

知识点名称：{kp_name}
描述：{kp_description}

要求：
- 题型只用 单选 或 阅读
- 每题 stem 必须先给一段"听力材料"（一段 2-4 句的英文对话或短独白），再提一个理解问题（中文或英文）
- 4 个选项标记 A-D，answer 是单个字母
- 难度贴近该知识点对应年级
- 每题含 explanation（≥ 20 字，说明从材料哪句得出答案）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "单选", "stem": "听力材料：\\nA: What time do you get up?\\nB: I get up at seven.\\n问题：B 几点起床？", "options": ["A. 6点","B. 7点","C. 8点","D. 9点"], "answer": "B", "explanation": "B 说 at seven，即 7 点。", "difficulty": 2}}
]"""

# ─── dictation（听写，拼写）──────────────────────────────────────────────────
_DICTATION_PROMPT = """请为以下知识点生成 {count} 道"听写/拼写"仿真题（暂用文本呈现，不含音频）。

知识点名称：{kp_name}
描述：{kp_description}

要求：
- 题型只用 填空
- 每题考查一个英文单词或短语的拼写：stem 给中文释义 + 一句含空白的英文例句（如"苹果：I eat an ___ every day."）
- options 为 null；answer 是要拼写的英文单词（多个合法拼写可用 | 分隔，如 "colour|color"）
- 每题含 explanation（≥ 20 字，可给音节/词性提示）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "填空", "stem": "苹果：I eat an ___ every day.", "options": null, "answer": "apple", "explanation": "apple /ˈæpəl/ 名词，意为苹果。", "difficulty": 1}}
]"""

# ─── writing（写作）──────────────────────────────────────────────────────────
_WRITING_PROMPT = """请为以下知识点生成 {count} 道"写作"仿真题。

知识点名称：{kp_name}
描述：{kp_description}

题型分配：
- 写作 ≥ 大部分：stem 是写作要求（如"以 My weekend 为题写 30-50 字"），options 为 null，answer 是 80-200 字参考范文
- 连线 0-2 道：stem 列左侧 1-4 项中文/句子片段、右侧 A-D 项英文，options 为 null，answer 用 | 分隔的对儿（"1-A|2-B|3-C"）

每题含 explanation（≥ 20 字，写作题说明评分要点/范文亮点）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "写作", "stem": "请以 My favorite animal 为题写 30 字短文。", "options": null, "answer": "My favorite animal is the dog. Dogs are friendly and loyal...", "explanation": "范文应包含主题句 + 2-3 个支持细节。", "difficulty": 3}}
]"""

_PROMPT_BY_DIMENSION = {
    "grammar": _GRAMMAR_PROMPT,
    "listening": _LISTENING_PROMPT,
    "dictation": _DICTATION_PROMPT,
    "writing": _WRITING_PROMPT,
}


def _is_deepseek_dev_mode() -> bool:
    return settings.deepseek_api_key.startswith("sk-placeholder")


# ─── dev-mock 题集（按维度）────────────────────────────────────────────────

def _mock_grammar(kp_name: str) -> list[AIGeneratedQuestion]:
    """语法维度：保留覆盖全部 7 种题型的固定集（兼容 count=9 全类型测试）。"""
    return [
        AIGeneratedQuestion(question_type="单选", stem=f"Mock 单选题 1 about {kp_name}.",
            options=["A. mock1", "B. mock2", "C. mock3", "D. mock4"], answer="B",
            explanation="Mock 解析：答案是 B 因为...", difficulty=2),
        AIGeneratedQuestion(question_type="单选", stem=f"Mock 单选题 2 about {kp_name}.",
            options=["A. opt1", "B. opt2", "C. opt3", "D. opt4"], answer="A",
            explanation="Mock 解析：选 A 是因为...", difficulty=3),
        AIGeneratedQuestion(question_type="填空", stem=f"Mock 填空题 1 about {kp_name}: He ___ play.",
            options=None, answer="can|may", explanation="Mock 解析：can 和 may 都接受。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"Mock 填空题 2 about {kp_name}: She ___ home.",
            options=None, answer="went", explanation="Mock 解析：went 是 go 的过去式。", difficulty=3),
        AIGeneratedQuestion(question_type="判断", stem=f"Mock 判断题 about {kp_name}: This rule applies always.",
            options=None, answer="错", explanation="Mock 解析：并非总是适用。", difficulty=1),
        AIGeneratedQuestion(question_type="完型", stem=f"Mock 完型 about {kp_name}: Tom ___ to school.",
            options=["A. go", "B. goes", "C. going", "D. went"], answer="B",
            explanation="Mock 解析：第三人称单数用 goes。", difficulty=2),
        AIGeneratedQuestion(question_type="阅读", stem=f"Mock 阅读 about {kp_name}: Read passage and answer. What is the topic?",
            options=["A. animals", "B. food", "C. school", "D. home"], answer="C",
            explanation="Mock 解析：根据文章主题判断。", difficulty=3),
        AIGeneratedQuestion(question_type="写作", stem=f"Mock 写作 about {kp_name}: 写一篇 30 字短文。",
            options=None, answer="This is a mock sample essay. It is short and demonstrates the topic clearly with simple English vocabulary.",
            explanation="Mock 参考范文。", difficulty=3),
        AIGeneratedQuestion(question_type="连线", stem=f"Mock 连线 about {kp_name}: 1.cat 2.dog 3.bird | A.猫 B.狗 C.鸟",
            options=None, answer="1-A|2-B|3-C", explanation="Mock 解析：对应关系。", difficulty=1),
    ]


def _mock_listening(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="单选",
            stem=f"听力材料（{kp_name}）：\nA: What time do you get up?\nB: I get up at seven.\n问题：B 几点起床？",
            options=["A. 6点", "B. 7点", "C. 8点", "D. 9点"], answer="B",
            explanation="Mock 解析：B 说 at seven，即 7 点。", difficulty=2),
        AIGeneratedQuestion(question_type="阅读",
            stem=f"听力短文（{kp_name}）：Tom likes apples. He eats one every morning.\n问题：Tom 早上吃什么？",
            options=["A. Banana", "B. Apple", "C. Orange", "D. Grape"], answer="B",
            explanation="Mock 解析：短文说 eats one(apple) every morning。", difficulty=2),
        AIGeneratedQuestion(question_type="单选",
            stem=f"听力对话（{kp_name}）：\nA: How are you?\nB: I'm fine, thank you.\n问题：B 现在怎么样？",
            options=["A. 很好", "B. 生病", "C. 难过", "D. 生气"], answer="A",
            explanation="Mock 解析：B 说 I'm fine。", difficulty=1),
    ]


def _mock_dictation(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）苹果：I eat an ___ every day.",
            options=None, answer="apple", explanation="Mock 解析：apple 名词，苹果。", difficulty=1),
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）学校：I go to ___ by bus.",
            options=None, answer="school", explanation="Mock 解析：school 名词，学校。", difficulty=1),
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）颜色：Red is my favourite ___.",
            options=None, answer="colour|color", explanation="Mock 解析：英式 colour / 美式 color 均可。", difficulty=2),
    ]


def _mock_writing(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="写作", stem=f"写作（{kp_name}）：请以 My weekend 为题写 30 字短文。",
            options=None, answer="On weekends I usually do my homework and play with my friends. I also help my mother...",
            explanation="Mock 参考范文：主题句 + 细节。", difficulty=3),
        AIGeneratedQuestion(question_type="连线", stem=f"连线（{kp_name}）：1.早上 2.中午 3.晚上 | A.evening B.morning C.noon",
            options=None, answer="1-B|2-C|3-A", explanation="Mock 解析：时间词对应。", difficulty=1),
        AIGeneratedQuestion(question_type="写作", stem=f"写作（{kp_name}）：介绍你最喜欢的食物，30-50 字。",
            options=None, answer="My favorite food is dumplings. They are delicious and my grandma makes them well...",
            explanation="Mock 参考范文。", difficulty=3),
    ]


_MOCK_BY_DIMENSION = {
    "grammar": _mock_grammar,
    "listening": _mock_listening,
    "dictation": _mock_dictation,
    "writing": _mock_writing,
}


def _make_mock_questions(
    kp_name: str, dimension: str, count: int
) -> list[AIGeneratedQuestion]:
    """dev mock：按维度取对应固定题集，循环填满 count 道。"""
    base = _MOCK_BY_DIMENSION.get(dimension, _mock_grammar)(kp_name)
    return [base[i % len(base)] for i in range(count)]


async def generate_questions(
    *,
    kp_name: str,
    kp_category: str,
    kp_description: str | None,
    dimension: str = "grammar",
    count: int = 5,
) -> list[AIGeneratedQuestion]:
    """为 1 个 KP 的指定维度生成 count 道仿真题。"""
    if _is_deepseek_dev_mode():
        return _make_mock_questions(kp_name, dimension, count)

    template = _PROMPT_BY_DIMENSION.get(dimension, _GRAMMAR_PROMPT)
    prompt = template.format(
        count=count,
        kp_name=kp_name,
        kp_category=kp_category,
        kp_description=kp_description or "(无)",
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=8192,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI 生题失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        # strict=False 允许字符串内出现裸换行/制表符（DeepSeek 偶尔直接输出真实换行）
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="AI 生题返回格式异常")

    try:
        return [AIGeneratedQuestion(**item) for item in data]
    except Exception as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_question_ai_service.py -v
```
Expected: 全部 PASS（原 2 个 + 新增 4 个）。

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/question_ai_service.py ../tests/services/test_question_ai_service.py
git commit -m "feat: dimension-aware question generation + fix max_tokens/json strict bugs"
```

---

## Task 2: `persist_questions` 写维度 + `list_questions_by_kp` 维度过滤

**Files:**
- Modify: `backend/app/services/question_service.py`
- Test: `tests/services/test_question_service.py`

- [ ] **Step 1: 写失败测试**

In `tests/services/test_question_service.py`, 在文件末尾追加：

```python
@pytest.mark.asyncio
async def test_persist_writes_dimension(db_session, seeded_kp):
    """persist_questions 传 dimension 时写入每行。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="vocabulary", kp_description="d",
        dimension="dictation", count=3,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs, dimension="dictation",
    )
    await db_session.flush()
    assert len(created) == 3
    assert all(str(r.dimension) == "dictation" for r in created)


@pytest.mark.asyncio
async def test_list_filters_by_dimension(db_session, seeded_kp):
    """list_questions_by_kp 给 dimension 时只返回该维度的题。"""
    # 写 listening 3 题 + dictation 3 题
    for dim, cat in (("listening", "grammar"), ("dictation", "vocabulary")):
        qs = await question_ai_service.generate_questions(
            kp_name=seeded_kp.name, kp_category=cat, kp_description="d",
            dimension=dim, count=3,
        )
        await question_service.persist_questions(
            db_session, kp_id=seeded_kp.id, questions=qs, dimension=dim,
        )
    await db_session.flush()

    listening = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, dimension="listening", limit=20,
    )
    assert len(listening) == 3
    assert all(q.question_type in ("单选", "阅读") for q in listening)

    dictation = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, dimension="dictation", limit=20,
    )
    assert len(dictation) == 3
    assert all(q.question_type == "填空" for q in dictation)


@pytest.mark.asyncio
async def test_list_without_dimension_returns_all(db_session, seeded_kp):
    """不传 dimension 时不过滤（向后兼容）。"""
    for dim in ("listening", "dictation"):
        qs = await question_ai_service.generate_questions(
            kp_name=seeded_kp.name, kp_category="grammar", kp_description="d",
            dimension=dim, count=3,
        )
        await question_service.persist_questions(
            db_session, kp_id=seeded_kp.id, questions=qs, dimension=dim,
        )
    await db_session.flush()
    allq = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, limit=20,
    )
    assert len(allq) == 6
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_question_service.py -k "dimension" -v
```
Expected: 3 个新测试 FAIL（`persist_questions() got an unexpected keyword argument 'dimension'`）。

- [ ] **Step 3: 改 `persist_questions` 接受并写 `dimension`**

In `backend/app/services/question_service.py`, 替换 `persist_questions` 的签名与 `SimulatedQuestion(...)` 构造：

签名改为（加 `dimension` 参数）：
```python
async def persist_questions(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    questions: list[AIGeneratedQuestion],
    dimension: str | None = None,
) -> list[SimulatedQuestion]:
    """按 (kp_id, stem) 幂等 upsert。dimension 写入新行（None 表示不分维度，向后兼容）。"""
```

`SimulatedQuestion(...)` 构造里，`difficulty=q.difficulty,` 之后加一行：
```python
            dimension=dimension,
```

（即 `status="published",` 前插入 `dimension=dimension,`。）

- [ ] **Step 4: 改 `list_questions_by_kp` 支持维度过滤**

In `backend/app/services/question_service.py`, 替换整个 `list_questions_by_kp`：

```python
async def list_questions_by_kp(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    dimension: str | None = None,
    limit: int = 5,
) -> list[SimQuestionOut]:
    stmt = (
        select(SimulatedQuestion)
        .where(
            SimulatedQuestion.knowledge_point_id == kp_id,
            SimulatedQuestion.status == "published",
        )
    )
    if dimension is not None:
        stmt = stmt.where(SimulatedQuestion.dimension == dimension)
    rows = (await db.execute(
        stmt.order_by(SimulatedQuestion.created_at).limit(limit)
    )).scalars().all()
    return [SimQuestionOut(
        id=r.id,
        question_type=str(r.question_type),
        stem=r.stem,
        options=r.options,
        difficulty=r.difficulty,
    ) for r in rows]
```

- [ ] **Step 5: 运行测试确认通过（含原有回归）**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/services/test_question_service.py -v
```
Expected: 全部 PASS（原有 + 3 个新增）。

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/question_service.py ../tests/services/test_question_service.py
git commit -m "feat: persist_questions writes dimension + list_questions_by_kp dimension filter"
```

---

## Task 3: API `practice-questions` 加 `dimension` query 参数

**Files:**
- Modify: `backend/app/api/v1/questions.py`
- Test: `tests/api/test_questions.py`

- [ ] **Step 1: 写失败测试**

In `tests/api/test_questions.py`, 先把 `_seed_kp_with_questions` 之外新增一个按维度灌题的 helper，再加测试。在文件末尾追加：

```python
async def _seed_kp_with_dimension_questions() -> uuid.UUID:
    """灌一个 KP：listening 3 题（单选/阅读）+ dictation 3 题（填空）。返回 kp_id。"""
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(),
            code=f"m3-dim-{uuid.uuid4().hex[:8]}",
            name="维度测试 KP",
            category="grammar",
            description="dim test",
            applicable_grades=["小学5年级"],
            applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        for dim in ("listening", "dictation"):
            qs = await question_ai_service.generate_questions(
                kp_name=kp.name, kp_category="grammar", kp_description="d",
                dimension=dim, count=3,
            )
            await question_service.persist_questions(
                s, kp_id=kp.id, questions=qs, dimension=dim,
            )
        await s.commit()
        return kp.id


@pytest.mark.asyncio
async def test_practice_questions_filter_by_dimension(client):
    """带 ?dimension=listening 只返回听力题（单选/阅读），不含听写填空。"""
    kp_id = await _seed_kp_with_dimension_questions()
    h = await _login(client, f"dim_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions?limit=10&dimension=listening",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) == 3
    assert all(it["question_type"] in ("单选", "阅读") for it in items)


@pytest.mark.asyncio
async def test_practice_questions_no_dimension_returns_all(client):
    """不带 dimension 返回该 KP 全部题（向后兼容）。"""
    kp_id = await _seed_kp_with_dimension_questions()
    h = await _login(client, f"dim2_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions?limit=20",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]) == 6
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/api/test_questions.py -k "dimension" -v
```
Expected: `test_practice_questions_filter_by_dimension` FAIL（dimension 参数被忽略，返回 6 题而非 3）。

- [ ] **Step 3: 端点加 `dimension` 参数**

In `backend/app/api/v1/questions.py`, 替换 `list_practice_questions`：

```python
@router.get("/kp/{kp_id}/practice-questions")
async def list_practice_questions(
    kp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
    dimension: str | None = Query(None, description="按维度过滤：listening/dictation/grammar/writing"),
):
    items = await question_service.list_questions_by_kp(
        db, kp_id=kp_id, dimension=dimension, limit=limit,
    )
    return make_ok([i.model_dump(mode="json") for i in items])
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/api/test_questions.py -v
```
Expected: 全部 PASS（原有 + 2 个新增）。

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/api/v1/questions.py ../tests/api/test_questions.py
git commit -m "feat: practice-questions API accepts dimension query param"
```

---

## Task 4: 前端透传维度（api + kp-content + v2-session + v2-exam）

**Files:**
- Modify: `frontend/miniprogram/src/api/questions.ts`
- Modify: `frontend/miniprogram/src/pages/curriculum/kp-content.vue`
- Modify: `frontend/miniprogram/src/pages/practice/v2-session.vue`
- Modify: `frontend/miniprogram/src/pages/practice/v2-exam.vue`

**说明：** 纯前端改动，小程序无单测，靠 `build:mp-weixin` 编译验证 + 人工实机验证。

- [ ] **Step 1: `api/questions.ts` 加 `dimension` 参数**

In `frontend/miniprogram/src/api/questions.ts`, 替换 `listPracticeQuestions`：

```typescript
export function listPracticeQuestions(
  kpId: string,
  limit = 5,
  dimension?: string,
): Promise<SimQuestionOut[]> {
  const data: Record<string, any> = { limit }
  if (dimension) data.dimension = dimension
  return request<SimQuestionOut[]>(
    `/api/v1/questions/kp/${kpId}/practice-questions`,
    { method: 'GET', data },
  )
}
```

- [ ] **Step 2: `kp-content.vue` 透传 `activeDim`**

In `frontend/miniprogram/src/pages/curriculum/kp-content.vue`, 替换 `goPractice` 和 `goExam`：

```typescript
function goPractice() {
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}&dim=${activeDim.value}` })
}

function goExam() {
  uni.navigateTo({ url: `/pages/practice/v2-exam?kp=${kpId.value}&count=10&dim=${activeDim.value}` })
}
```

- [ ] **Step 3: `v2-session.vue` 读取并透传 `dim`**

In `frontend/miniprogram/src/pages/practice/v2-session.vue`, `<script setup>` 顶部加一个 ref（在 `const kpId = ref('')` 之后）：

```typescript
const dim = ref('')
```

替换 `onLoad`：

```typescript
onLoad(async (q: any) => {
  kpId.value = q.kp || ''
  dim.value = q.dim || ''
  if (!kpId.value) {
    uni.showToast({ title: '缺少 kp 参数', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  try {
    questions.value = await listPracticeQuestions(kpId.value, 5, dim.value || undefined)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})
```

- [ ] **Step 4: `v2-exam.vue` 读取并透传 `dim`**

In `frontend/miniprogram/src/pages/practice/v2-exam.vue`, `<script setup>` 顶部加（在 `const kpId = ref('')` 之后）：

```typescript
const dim = ref('')
```

替换 `onLoad`：

```typescript
onLoad(async (q: any) => {
  kpId.value = q.kp || ''
  dim.value = q.dim || ''
  const count = Number(q.count) || 10
  if (!kpId.value) {
    uni.showToast({ title: '缺少 kp 参数', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  try {
    questions.value = await listPracticeQuestions(kpId.value, count, dim.value || undefined)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})
```

- [ ] **Step 5: 编译验证**

Run:
```bash
cd frontend/miniprogram && npm run build:mp-weixin
```
Expected: 编译成功，无 TypeScript 报错。（若项目用其他包管理器/脚本名，按 `package.json` 实际脚本调整。）

- [ ] **Step 6: Commit**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/miniprogram/src/api/questions.ts \
        frontend/miniprogram/src/pages/curriculum/kp-content.vue \
        frontend/miniprogram/src/pages/practice/v2-session.vue \
        frontend/miniprogram/src/pages/practice/v2-exam.vue
git commit -m "feat: frontend passes dimension from KP tab to practice/exam pages"
```

---

## Task 5: `seed_questions.py` 按维度循环生题

**Files:**
- Modify: `backend/scripts/seed_questions.py`

**说明：** 让脚本能为每个 KP 的 4 个维度分别生题（每维度 N 题）。默认仍可用 dev-mock 跑通流程（不花钱）。真实 DeepSeek 重灌见 Task 8（需预算确认）。

- [ ] **Step 1: 改 `seed_one_kp` 按维度循环**

In `backend/scripts/seed_questions.py`, 在 import 区后、`seed_one_kp` 前加维度常量：

```python
DIMENSIONS = ["listening", "dictation", "grammar", "writing"]
```

替换整个 `seed_one_kp`：

```python
async def seed_one_kp(kp_id: _uuid.UUID, count: int = 5) -> int:
    """为 1 个 KP 的 4 个维度各生成 count 道题；返回总行数（含已存在）。"""
    total = 0
    async with _async_session_factory() as db:
        kp = (await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )).scalar_one_or_none()
        if kp is None:
            print(f"  [skip] KP {kp_id} 不存在")
            return 0

        for dim in DIMENSIONS:
            print(f"  [gen]  {kp.name} · {dim} ...", end=" ", flush=True)
            qs = await question_ai_service.generate_questions(
                kp_name=kp.name,
                kp_category=str(kp.category),
                kp_description=kp.description,
                dimension=dim,
                count=count,
            )
            rows = await question_service.persist_questions(
                db, kp_id=kp.id, questions=qs, dimension=dim,
            )
            total += len(rows)
            print(f"✓ {len(rows)} 道")
        await db.commit()
        return total
```

- [ ] **Step 2: dev-mock 跑通验证（不花钱）**

先确认存在一个真实 KP id（小学5上已灌），取一个 KP：
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -c "
import asyncio
from sqlalchemy import select
from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
async def main():
    async with _async_session_factory() as s:
        kp = (await s.execute(select(KnowledgePoint).limit(1))).scalar_one_or_none()
        print(kp.id if kp else 'NO KP')
asyncio.run(main())
"
```
用 dev-mock（临时把 key 设为 placeholder，不动 .env）跑该 KP：
```bash
cd backend && DEEPSEEK_API_KEY=sk-placeholder-seed-test \
  DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer \
  python scripts/seed_questions.py --kp <上一步打印的 KP id> --count 3
```
Expected: 打印 4 行（listening/dictation/grammar/writing 各 ✓ 3 道）。

> 注意：用 `DEEPSEEK_API_KEY=sk-placeholder-...` 前缀显式覆盖会触发 dev-mock。Settings 仍会加载 `.env` 的其它必需变量（database_url 等）；只覆盖 key 不影响 DB 连接。**不要**用真实 key 跑此步（会花钱）。

- [ ] **Step 3: 清理验证产生的 mock 题（避免污染真实题库）**

```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -c "
import asyncio
from sqlalchemy import delete
from app.core.database import _async_session_factory
from app.models.d12_v2_exams import SimulatedQuestion
KP_ID = '<上面用的 KP id>'
async def main():
    async with _async_session_factory() as s:
        await s.execute(delete(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == KP_ID))
        await s.commit()
        print('cleaned')
asyncio.run(main())
"
```
Expected: 打印 `cleaned`。（仅删验证时灌入的 mock 题。）

- [ ] **Step 4: Commit**

```bash
cd backend && git add scripts/seed_questions.py
git commit -m "feat: seed_questions generates per-dimension questions"
```

---

## Task 6: 全量回归 + D-091 归档

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 跑全量后端测试**

Run:
```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer python -m pytest ../tests/ -q
```
Expected: 全绿（无新增失败）。若有失败，回到对应 Task 修复后再继续。

- [ ] **Step 2: 写 D-091 归档条目**

In `docs/决策归档.md`, 在顶部 `---`（约第 6 行）之后、D-090 之前插入（格式与既有条目一致）：

```markdown
## D-091 维度感知练习题（2026-06-02）

**背景：** KP 详情页有听力/听写/语法/写作四个 tab，但练习/模拟考四个 tab 共用同一批语法题。用户要求各维度练习题各有特点。

**结论：**
1. `simulated_questions` 加可空 `dimension` 列（复用 content_dimension 枚举，迁移 0014）。
2. AI 生题改为按维度：听力=文本近似的对话/短文理解（单选/阅读），听写=拼写填空，语法=原混合，写作=作文/连线。真音频留待 M2.5。
3. `generate_questions`/`persist_questions` 加 dimension 参数；`list_questions_by_kp` + `practice-questions` API 支持 dimension 过滤；前端 KP tab 把 activeDim 透传给练习/模拟考页。
4. 顺手修了 question_ai_service 残留的 max_tokens=4096→8192 与 json.loads strict=False 两个 bug。
5. dimension 全程可空、默认 grammar，旧数据/旧测试/旧 seed 行为不变（向后兼容）。

**测试：** 后端全量 pytest 通过；新增维度感知 mock、persist 写维度、list/API 维度过滤断言。前端 build:mp-weixin 编译通过。

**未做：** 真听力/听写音频（M2.5 TTS）；真实 DeepSeek 重灌全量题库（需预算确认，过渡期旧 NULL-维度题不出现在任何 tab，重灌后才有维度题）。

**影响范围：** 迁移 0014；question_ai_service / question_service / api/v1/questions；前端 api/questions.ts + kp-content/v2-session/v2-exam；seed_questions。

**相关：** D-079（V2 演进）、D-090（内容试点）。
```

- [ ] **Step 3: Commit + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add docs/决策归档.md
git commit -m "docs: archive D-091 dimension-aware practice questions"
git push
```

---

## Task 7（可选，需预算确认）：真实 DeepSeek 重灌小学5上题库

> **⚠️ 花钱步骤——执行前必须向用户确认预算。** 默认**不执行**。仅当用户明确确认预算后才跑。

**背景：** Task 0-6 完成后，代码支持维度题，但 DB 里小学5上还没有"维度题"（旧题是 NULL 维度，不会出现在任何 tab）。需用真实 DeepSeek 为每个 KP × 4 维度生题。

**成本估算：** 小学5上 8 单元约 50-60 个 KP × 4 维度 × 每维度 1 次调用 ≈ 200-240 次 DeepSeek 调用。参考 D-090 单元生成成本（<$0.1/学期），题库重灌约 $0.3-0.8。**以实际为准，先小跑 1 个单元看花费再决定全学期。**

- [ ] **Step 1: 向用户确认预算**（用 AskUserQuestion）；得到明确"是"后再继续。

- [ ] **Step 2: 先跑 1 个单元验证**

```bash
cd backend && DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/enggramer \
  python scripts/seed_questions.py --textbook 译林版 --grade 小学5年级 --semester 上 --unit-no 1 --count 3
```
（用 `.env` 里的真实 key，会花钱。）检查输出质量 + 实机看效果。

- [ ] **Step 3: 质量 OK 后再跑全学期 U1-U8**（逐单元，避免一次性大额）。每单元一条命令，`--unit-no` 改 2..8。

- [ ] **Step 4: 实机验证四维度练习题确有差异，归档花费到 D-091（追加一行实际成本）。**

---

## 执行后最终审查（subagent-driven 收尾）

全部 Task 完成后，派一个 final code-reviewer 子代理审查整条分支：迁移可逆、维度过滤无 SQL 注入风险（dimension 走参数绑定）、向后兼容（NULL 维度不破坏旧流程）、前端透传链路完整、测试覆盖维度过滤。然后用 superpowers:finishing-a-development-branch 收尾。
