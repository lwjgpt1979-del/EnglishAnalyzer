# P1 词力通词汇学习模块（MVP 核心背词闭环）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 交付词力通 MVP 核心背词闭环——每日任务（新词 + 到期复习词，SM-2 调度）、词卡展示、`看词选义/看义选词`两种基础题型、答题更新熟练度、每日新词上限按会员档位。

**Architecture:** 纯复用既有 `vocabulary_words`（词库，已灌数据）+ `vocabulary_learning`（SM-2 状态表，字段齐全：interval_days/repetitions/easiness_factor/next_review_at/last_reviewed_at/level）。新增 `vocabulary_service`（SM-2 调度 + 判分）+ `api/v1/vocabulary.py` 路由 + 小程序「词力通」页。**零 DB 迁移**。新词 = 该生无 learning 记录的 vocabulary_words；档位每日新词上限硬编码映射（free=5/basic=10/pro=30/promax=50，后台可配置留后续）。

**Tech Stack:** FastAPI + SQLAlchemy async；uni-app Vue3 小程序。

**先不做（后续切片）：** 听音辨词/拼写填空/例句填空题型、错词本与错题联动、打卡连续激励、提醒推送、词库范围按档位限制、词库范围按学期过滤。

---

### Task 1: Schemas —— 词力通数据结构

**Files:**
- Create: `backend/app/schemas/vocabulary.py`
- Test: `tests/services/test_vocabulary_service.py`（schema 构造冒烟）

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, Field

class WordCardOut(BaseModel):
    """词卡（学习展示用，不含会泄漏答案的题目结构）。"""
    word_id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] | dict  # JSONB 原样透出
    examples: list | dict | None = None
    difficulty: int
    level: str          # new/learning/review/mastered
    is_new: bool         # 今日新词 or 复习词

class DailyTaskOut(BaseModel):
    new_words: list[WordCardOut]
    review_words: list[WordCardOut]
    new_count: int
    review_count: int
    new_limit: int       # 当前档位每日新词上限

class VocabAnswerIn(BaseModel):
    word_id: uuid.UUID
    correct: bool
    hesitant: bool = Field(False, description="记得但不确定：熟练度不升级、间隔不延长")

class VocabAnswerResult(BaseModel):
    word_id: uuid.UUID
    level: str
    repetitions: int
    interval_days: int
    next_review_at: str   # ISO
```

- [ ] Step 1: 写 schema 冒烟测试（构造各 model）
- [ ] Step 2: 跑测试确认失败（模块不存在）
- [ ] Step 3: 实现 schema
- [ ] Step 4: 跑测试确认通过
- [ ] Step 5: Commit `feat(backend): 词力通 schemas`

### Task 2: Service —— SM-2 调度 + 判分 + 档位限额

**Files:**
- Create: `backend/app/services/vocabulary_service.py`
- Test: `tests/services/test_vocabulary_service.py`

**SM-2 核心（纯函数，便于测试）：**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.d5_learning import VocabularyWord, VocabularyLearning
from app.services import membership_service

_DAILY_NEW_LIMIT = {"free": 5, "basic": 10, "pro": 30, "promax": 50}  # 后台可配置留后续

def _level_for(repetitions: int) -> str:
    if repetitions <= 0: return "new"
    if repetitions <= 2: return "learning"
    if repetitions == 3: return "review"
    return "mastered"

def sm2(*, correct: bool, hesitant: bool, repetitions: int,
        interval_days: int, ef: float) -> tuple[int, int, float]:
    """返回 (repetitions, interval_days, ef)。q: 对=5 / 犹豫=3 / 错=2。"""
    q = 2 if not correct else (3 if hesitant else 5)
    # EF 更新（下限 1.3）
    ef = max(1.3, ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    if q < 3:                       # 答错：重置
        return 0, 1, ef
    if hesitant:                    # 犹豫：不升级、间隔不延长
        return repetitions, max(1, interval_days), ef
    repetitions += 1
    if repetitions == 1: interval = 1
    elif repetitions == 2: interval = 3
    elif repetitions == 3: interval = 7
    elif repetitions == 4: interval = 15
    else: interval = 30
    return repetitions, interval, ef

async def _daily_new_limit(db, *, student_id) -> int:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    return _DAILY_NEW_LIMIT.get(tier, 5)
```

**`get_daily_task(db, *, student_id)`**：
- review_words：`vocabulary_learning` 中 `next_review_at <= now` 的词（join vocabulary_words），按 next_review_at 升序。
- new_words：`vocabulary_words` 中该生**无** learning 记录的，按 difficulty 升序，limit = 档位上限。
- 返回 DailyTaskOut（is_new 标记、new_limit）。

**`submit_answer(db, *, student_id, word_id, correct, hesitant)`**：
- 取该生该词 learning 行；无则视为新词首学，新建（repetitions=0, interval=1, ef=2.5, level=new）。
- 调 `sm2(...)` 得新 (reps, interval, ef)；`level=_level_for(reps)`；`next_review_at=now+interval天`；`last_reviewed_at=now`；写回。
- 返回 VocabAnswerResult。

- [ ] Step 1: 写测试（见下）
- [ ] Step 2: 跑测试确认失败
- [ ] Step 3: 实现 service
- [ ] Step 4: 跑测试确认通过
- [ ] Step 5: Commit `feat(backend): 词力通 SM-2 调度 + 判分 service`

**测试要点（`test_vocabulary_service.py`）：**
```python
def test_sm2_correct_progression():
    # 连续答对：repetitions 递增，interval 走 1→3→7→15→30
    reps, iv, ef = 0, 1, 2.5
    seq = []
    for _ in range(6):
        reps, iv, ef = vocabulary_service.sm2(correct=True, hesitant=False, repetitions=reps, interval_days=iv, ef=ef)
        seq.append(iv)
    assert seq[:5] == [1, 3, 7, 15, 30]

def test_sm2_wrong_resets():
    reps, iv, ef = vocabulary_service.sm2(correct=False, hesitant=False, repetitions=3, interval_days=7, ef=2.5)
    assert reps == 0 and iv == 1

def test_sm2_hesitant_no_advance():
    reps, iv, ef = vocabulary_service.sm2(correct=True, hesitant=True, repetitions=2, interval_days=3, ef=2.5)
    assert reps == 2 and iv == 3

# DB 集成（用 _async_session_factory + 建 student + 灌几个 vocabulary_words）：
# test_daily_task_returns_new_within_limit：free 档新词 ≤5；
# test_submit_creates_then_updates：首次提交建 learning 行；再答对 level 升级、next_review_at 在未来；
# test_submit_wrong_resets_level：答错 level 回 new、next_review_at≈当天。
```

### Task 3: API 路由 + 注册

**Files:**
- Create: `backend/app/api/v1/vocabulary.py`
- Modify: `backend/app/api/v1/router.py`（import + include_router）
- Test: `tests/api/test_vocabulary.py`

**端点（均 `Depends(get_current_user)`；写操作用 `get_rls_db`）：**
- `GET /vocabulary/daily-task` → `BaseResponse[DailyTaskOut]`
- `POST /vocabulary/answer` body `VocabAnswerIn` → `BaseResponse[VocabAnswerResult]`（末尾 `await db.commit()`）

router.py 加：
```python
from app.api.v1.vocabulary import router as vocabulary_router
v1_router.include_router(vocabulary_router)
```

- [ ] Step 1: 写 API 测试（登录学生 → GET daily-task 200 结构 → POST answer 200 + level 变化；未登录 401）
- [ ] Step 2: 跑测试确认失败
- [ ] Step 3: 实现路由 + 注册
- [ ] Step 4: 跑测试确认通过 + 后端全量回归
- [ ] Step 5: Commit `feat(backend): 词力通 API（daily-task + answer）`

### Task 4: 前端「词力通」页

**Files:**
- Create: `frontend/miniprogram/src/pages/vocabulary/index.vue`
- Modify: `frontend/miniprogram/src/pages.json`（注册路由）
- Create: `frontend/miniprogram/src/api/vocabulary.ts`
- Modify: `frontend/miniprogram/src/types/api.ts`（DailyTask/WordCard/AnswerResult 类型）
- Modify: 学习中心入口（首页或 profile 加「词力通」入口卡，参照现有练习入口）

**页面流程（MVP）：** 进页拉 `daily-task` → 先过新词词卡（展示 word/音标/释义/例句，「记住了/没记住」）→ 本批新词 + 复习词进入题型测试（看词选义/看义选词，4 选 1，选项从其它词释义/词随机取）→ 每题调 `POST /answer` → 末尾显示今日完成数据（新学 X / 复习 X / 正确率）。

- [ ] Step 1: api/vocabulary.ts（getDailyTask / submitAnswer）+ 类型
- [ ] Step 2: 词力通页（词卡 + 两题型 + 完成统计）
- [ ] Step 3: 学习中心/首页加入口
- [ ] Step 4: `npm run build:mp-weixin` 验证可编译
- [ ] Step 5: Commit `feat(frontend): 词力通背词页`

### Task 5: 集成验证 + 归档 D-100

- [ ] Step 1: 后端全量 `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly` 绿
- [ ] Step 2: 前端 build 通过
- [ ] Step 3: docs/决策归档.md 顶部加 D-100（SM-2 闭环 MVP + 档位限额 + 明确"先不做"清单 = 听音/拼写/例句题型、错词本、打卡、提醒、词库范围）
- [ ] Step 4: Commit +（征得同意后）push

---

## 备注
- **档位每日新词上限**当前硬编码 `_DAILY_NEW_LIMIT`，与需求 5.6「学生服务次数限额」后台可配置一致性留后续（可挪到 system_configs，类比 D-097 定价）。
- **错词本**（6.4.6）依赖本模块的"答错"事件，是天然的下一切片。
- **新词词源**：MVP 取全库未学词按难度升序；按学期/教材过滤词库范围属档位权限，留后续。
- **词库现状（已核）**：`vocabulary_words` 已有 173 行，但均为 M2 dev-mock 占位（`word='word1_1'`、释义 `'mock 释义N'`、无音标）。背词闭环逻辑可跑通，但词面内容为假——真实词库重灌（花钱）属独立后续项，本切片只交付功能闭环。
- **唯一约束（已核）**：`vocabulary_learning` 有 `(student_id, word_id)` 唯一约束，submit_answer upsert 安全。
- **选择题干扰项（Task 4 定）**：MVP 倾向前端从当批 new+review 词池就地随机取 3 个干扰项；词池过小则后端 daily-task 可额外多带几个干扰词。Task 4 实现时定。
