# engGramer Tech Spec — 技术规格书

> 版本：v1.0 | 日期：2026-05-24 | 状态：Section 1-3 已确认，Section 4+ 进行中

---

## Section 1：系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Taro 微信小程序                        │
│     学生端 / 老师端 / 亲人端（同一小程序，角色路由）         │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTPS / WebSocket
┌───────────────────▼─────────────────────────────────────┐
│               腾讯云 API 网关 / CLB                       │
│        （限流 + SSL 卸载 + 路由转发）                      │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│                FastAPI 应用层（CVM / TKE）                │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Auth 模块   │  │  业务路由层   │  │  后台管理接口  │  │
│  │ (JWT+微信auth)│  │  /api/v1/…  │  │  /admin/…     │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │                    Service 层                       │ │
│  │  OCRService │ AIService │ MemberService │ SMService │ │
│  └────────────────────────────────────────────────────┘ │
└──────┬───────────────────────────────────────┬──────────┘
       │                                       │
┌──────▼──────┐                    ┌───────────▼──────────┐
│  异步任务队列 │                    │      数据层           │
│  (ARQ/Redis)│                    │  PostgreSQL（CDB）    │
│             │                    │  Redis（缓存/会话）   │
│ OCR任务     │                    │  COS（图片/音频）     │
│ AI诊断任务  │                    └──────────────────────┘
│ 通知任务    │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                   外部服务层                              │
│  阿里云OCR（印刷体）│ 腾讯云OCR（手写体）│ DeepSeek/Claude │
│  微信支付          │ 企业微信通知       │ 微信订阅消息      │
└─────────────────────────────────────────────────────────┘
```

### 关键技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 后端框架 | **FastAPI** | 原生异步，天然适合 OCR/LLM 长耗时 IO 调用 |
| 数据库 | **PostgreSQL** | JSONB、RLS、UUID 支持完善，SaaS 首选 |
| 云平台 | **腾讯云** | 小程序生态直连，手写体 OCR 已在腾讯，内网流量免费 |
| 小程序框架 | **Taro（React 语法）** | 一套代码，后期可扩展 H5/App |
| 任务队列 | **ARQ**（基于 asyncio）| FastAPI 原生异步，无需 Celery 多进程 |
| 实时通知 | WebSocket（站内）+ 微信订阅消息（离线）| 覆盖在线/离线两种场景 |
| 图片存储 | **腾讯云 COS** | 同云内网传输免费，支持图片处理 URL |
| 后台管理 UI | P2 再做，MVP 用接口 + 直接操作 DB | 降低 MVP 开发量 |

---

## Section 2：多租户数据隔离策略

### 选型：行级隔离（Shared Schema + tenant_id）

所有租户共用同一套表结构，每张业务表带 `institution_id`（机构）或 `user_id`（用户）列，配合 **PostgreSQL Row-Level Security（RLS）** 在数据库层自动过滤。

```sql
-- 示例：wrong_questions 表启用 RLS
ALTER TABLE wrong_questions ENABLE ROW LEVEL SECURITY;
CREATE POLICY student_isolation ON wrong_questions
    USING (student_id = current_setting('app.current_user_id')::UUID);
```

### 实施原则

```
1. 所有业务表必须有 user_id 或 institution_id（至少一个）
2. 所有查询必须带租户过滤条件（Service 层强制，不依赖调用方）
3. C 端独立用户：institution_id = NULL
4. 机构学生：institution_id = 所属机构 ID
5. FastAPI 中间件在每个请求注入 current_user，Service 层用它过滤
6. 接口层 + RLS 双重校验，防止代码 Bug 导致跨租户泄漏
```

### 租户层级

```
平台（1）→ 机构（N）→ 老师（N）→ 学生（N）→ 亲人（N，最多4位）
```

---

## Section 3：核心数据模型（34 张表）

> 共 9 个业务域，所有表使用 UUID 主键，时间戳字段统一用 TIMESTAMPTZ。

---

### 域 1：用户与租户（8 张表）

```
users（所有角色共用基础表）
├── id              UUID PK
├── openid          VARCHAR UNIQUE       ← 微信 openid，登录唯一标识
├── phone           VARCHAR
├── nickname        VARCHAR
├── avatar_url      VARCHAR
├── role            ENUM(student / teacher / relative /
│                        institution_admin / platform_admin)
├── is_active       BOOLEAN DEFAULT true
├── created_at      TIMESTAMPTZ
└── updated_at      TIMESTAMPTZ

institutions（机构）
├── id              UUID PK
├── name            VARCHAR
├── contact_phone   VARCHAR
├── commission_rate DECIMAL              ← 分成比例（见 PRD 5.8）
├── status          ENUM(pending / active / suspended)
└── created_at      TIMESTAMPTZ

students（学生扩展，1:1 users）
├── id              UUID PK → users.id
├── institution_id  UUID FK → institutions  ← NULL = C 端独立用户
├── grade           VARCHAR              ← 年级（7/8/9/10/11/12）
├── textbook_ver    VARCHAR              ← 教材版本（人教版/外研版/北师大版…）
├── semester        ENUM(上/下)
├── info_change_count_month  INT DEFAULT 0   ← 防滥用计数（5.6 后台配置上限）
└── info_change_reset_date   DATE

teachers（老师扩展，1:1 users）
├── id              UUID PK → users.id
├── institution_id  UUID FK → institutions  ← NULL = C 端认证老师
├── cert_status     ENUM(uncertified / pending / certified / rejected)
└── cert_doc_url    VARCHAR              ← 认证材料 COS 路径

relatives（亲人扩展，1:1 users）
└── id              UUID PK → users.id

student_relatives（学生-亲人绑定，M:N，每学生最多 4 位亲人）
├── id              UUID PK
├── student_id      UUID FK → users
├── relative_id     UUID FK → users
├── relationship    VARCHAR              ← 爸爸 / 妈妈 / 爷爷…
├── is_active       BOOLEAN
└── bound_at        TIMESTAMPTZ
    [CONSTRAINT: COUNT(relative_id) WHERE student_id <= 4]

teacher_students（老师-学生直接绑定关系）
├── id              UUID PK
├── teacher_id      UUID FK → users
├── student_id      UUID FK → users
├── bind_type       ENUM(institution_assigned /  ← 机构分配（不可自主换绑）
│                        self_bound)             ← 学生自主绑定（可换绑）
├── institution_id  UUID FK → institutions (nullable)
├── is_active       BOOLEAN
├── bound_at        TIMESTAMPTZ
└── unbound_at      TIMESTAMPTZ (nullable)
    [UNIQUE: (teacher_id, student_id) WHERE is_active = true]

invite_codes（邀请码）
├── id              UUID PK
├── code            VARCHAR(6) UNIQUE    ← 6 位随机码
├── type            ENUM(relative_bind /     ← 亲人绑定学生
│                        institution_join)   ← 机构邀请学生/老师
├── issuer_id       UUID FK → users      ← 发码人（学生 / 机构管理员）
├── target_id       UUID FK → users (nullable) ← 接受者（绑定成功后填入）
├── expires_at      TIMESTAMPTZ          ← 默认 24h 有效
├── used_at         TIMESTAMPTZ (nullable)
└── created_at      TIMESTAMPTZ
```

---

### 域 2：会员与支付（3 张表）

```
memberships（会员状态，每用户永远只有 1 条 active 记录）
├── id              UUID PK
├── user_id         UUID FK → users
├── tier            ENUM(free / basic / pro / promax)
├── started_at      TIMESTAMPTZ
├── expires_at      TIMESTAMPTZ
└── is_active       BOOLEAN

orders（订单）
├── id              UUID PK
├── order_no        VARCHAR UNIQUE       ← 业务单号（展示用）
├── payer_id        UUID FK → users      ← 付款人（可能是亲人）
├── beneficiary_id  UUID FK → users      ← 受益学生
├── order_type      ENUM(new / renew / upgrade)
├── tier            ENUM(basic / pro / promax)
├── duration_months INT                  ← 6 / 12 / 24 / 36
├── amount_fen      INT                  ← 金额（分，避免浮点精度问题）
├── status          ENUM(pending / paid / refunded / partial_refunded)
├── wx_transaction_id  VARCHAR
├── paid_at         TIMESTAMPTZ
└── created_at      TIMESTAMPTZ

refund_records（退款记录）
├── id              UUID PK
├── order_id        UUID FK → orders
├── amount_fen      INT
├── refund_type     ENUM(standard_7d / prorated / appeal)
├── appeal_no_this_year  INT DEFAULT 0  ← 年度申诉计数（独立计数器，见 PRD 4.5.1）
├── status          ENUM(pending / approved / rejected / completed)
├── reason          TEXT
└── created_at      TIMESTAMPTZ
```

---

### 域 3：错题与 AI 诊断（3 张表）

```
wrong_questions（错题主记录）
├── id              UUID PK
├── student_id      UUID FK → users
├── institution_id  UUID FK → institutions (nullable)  ← NULL = C 端
├── source_image_url  VARCHAR             ← COS 路径
├── question_text   TEXT                 ← OCR 识别后文本
├── student_answer  TEXT
├── correct_answer  TEXT
├── question_type   ENUM(单选/完型/阅读/作文/其他)
├── difficulty      SMALLINT (1-5)
├── tags            JSONB                ← AI 自由标签（如"审题失误"）
│                                          知识点关联见 wrong_question_knowledge_points
├── is_mastered     BOOLEAN DEFAULT false
├── mastered_at     TIMESTAMPTZ
└── created_at      TIMESTAMPTZ

ocr_tasks（OCR 异步任务状态）
├── id              UUID PK
├── wrong_question_id  UUID FK → wrong_questions
├── status          ENUM(pending / processing / completed / failed)
├── provider        ENUM(aliyun_print / tencent_handwrite)
├── raw_result      JSONB                ← 原始 OCR 响应备存
├── retry_count     SMALLINT DEFAULT 0
├── created_at      TIMESTAMPTZ
└── completed_at    TIMESTAMPTZ

ai_analyses（AI 诊断结果）
├── id              UUID PK
├── wrong_question_id  UUID FK → wrong_questions
├── student_id      UUID FK → users
├── llm_provider    ENUM(deepseek / claude)
├── error_types     JSONB                ← ["语法错误","词汇混淆"]
├── knowledge_points  JSONB             ← 关联知识点（冗余存，方便展示）
├── diagnosis       TEXT                ← AI 诊断正文
├── suggestions     TEXT                ← 学习建议
├── tokens_used     INT
└── created_at      TIMESTAMPTZ
```

---

### 域 4：知识体系（静态知识树，平台内置，5 张表）

```
knowledge_points（语法/能力知识点树）
├── id              UUID PK
├── code            VARCHAR UNIQUE       ← 固定编码，如 "GRAM_PRES_PERFECT"
├── name            VARCHAR              ← "现在完成时"
├── category        ENUM(grammar / vocabulary / reading / writing / listening)
├── description     TEXT
├── applicable_grades     VARCHAR[]      ← ["7","8","9"]
├── applicable_textbooks  VARCHAR[]      ← ["人教版","外研版","北师大版"]
├── parent_id       UUID FK → knowledge_points (nullable)  ← 树形结构
└── sort_order      INT

示例树形结构：
  语法 → 时态 → 现在完成时 → 现在完成时·肯定句
                           → 现在完成时·否定与疑问句

curriculum_units（教材单元目录）
├── id              UUID PK
├── textbook_version VARCHAR             ← "人教版" / "外研版" / "北师大版"
├── grade           VARCHAR             ← "7" / "8" / "9" …
├── semester        ENUM(上/下)
├── unit_no         INT
└── unit_title      VARCHAR             ← "Unit 3 I'm more outgoing than…"

unit_knowledge_points（单元 ↔ 知识点）
├── unit_id         UUID FK → curriculum_units
└── knowledge_point_id UUID FK → knowledge_points
    [PRIMARY KEY: (unit_id, knowledge_point_id)]

curriculum_words（单元词汇表，词力通核心数据源）
├── unit_id         UUID FK → curriculum_units
├── word_id         UUID FK → vocabulary_words
├── is_core         BOOLEAN              ← 核心词 / 扩展词
└── sort_order      INT
    [PRIMARY KEY: (unit_id, word_id)]

wrong_question_knowledge_points（错题 ↔ 知识点，AI 诊断后写入）
├── wrong_question_id UUID FK → wrong_questions
└── knowledge_point_id UUID FK → knowledge_points
    [PRIMARY KEY: (wrong_question_id, knowledge_point_id)]
```

**联动逻辑：**
```
学生选择：年级 + 教材版本 + 学期
    ↓ 锁定 curriculum_units
    ↓
词力通：从 curriculum_words 拉取词汇 + 错题高频词 → vocabulary_learning（SM-2）
AI诊断：LLM 输出 knowledge_point.code → wrong_question_knowledge_points
学情报告：按 knowledge_points.category 聚合 → 语法/词汇/阅读掌握度
```

---

### 域 5：学习功能（词力通 / 作文 / 听力 / 打卡，5 张表）

```
vocabulary_words（全局词库）
├── id              UUID PK
├── word            VARCHAR
├── phonetic        VARCHAR
├── definitions     JSONB                ← [{pos:"n.", meaning:"苹果"}]
├── examples        JSONB                ← 例句列表
└── difficulty      SMALLINT (1-5)

vocabulary_learning（SM-2 学习状态，per 学生 per 词）
├── id              UUID PK
├── student_id      UUID FK → users
├── word_id         UUID FK → vocabulary_words
├── interval_days   INT DEFAULT 1        ← SM-2 间隔天数
├── repetitions     INT DEFAULT 0        ← SM-2 重复次数
├── easiness_factor DECIMAL DEFAULT 2.5  ← SM-2 难度因子
├── next_review_at  TIMESTAMPTZ
├── last_reviewed_at  TIMESTAMPTZ
└── level           ENUM(new / learning / review / mastered)
    [UNIQUE: (student_id, word_id)]

essays（作文精修）
├── id              UUID PK
├── student_id      UUID FK → users
├── wrong_question_id  UUID FK (nullable)  ← 可关联来源错题
├── original_text   TEXT
├── polished_text   TEXT                 ← AI 精修后
├── dimensions      JSONB                ← {语法:85, 词汇:90, 逻辑:78, 内容:88}
├── round_count     SMALLINT DEFAULT 1   ← 精修轮次（Pro 上限见 5.6）
├── status          ENUM(draft / processing / completed)
└── created_at      TIMESTAMPTZ

listening_records（听力跟读记录）
├── id              UUID PK
├── student_id      UUID FK → users
├── audio_url       VARCHAR              ← 学生录音 COS 路径
├── reference_url   VARCHAR              ← 原始参考音频 COS 路径
├── score           DECIMAL              ← 发音评分（0-100）
├── feedback        JSONB                ← AI 反馈详情
└── created_at      TIMESTAMPTZ

study_checkins（每日打卡记录）
├── id              UUID PK
├── student_id      UUID FK → users
├── checkin_date    DATE                 ← 自然日
├── new_words_count INT                  ← 当日学新词数
├── review_done     BOOLEAN              ← 是否完成全部复习词
├── streak_days     INT                  ← 当前连续天数（冗余存，避免重算）
└── created_at      TIMESTAMPTZ
    [UNIQUE: (student_id, checkin_date)]
```

---

### 域 6：AI 题库与练习（2 张表）

```
ai_questions（AI 仿真题库，预生成存库）
├── id              UUID PK
├── knowledge_point_id UUID FK → knowledge_points
├── unit_id         UUID FK → curriculum_units (nullable)
├── question_type   ENUM(单选 / 填空 / 完型 / 阅读 / 写作)
├── difficulty      SMALLINT (1-5)
├── content         JSONB                ← {stem:"…", options:[…], answer:"A", explanation:"…"}
├── is_active       BOOLEAN DEFAULT true
├── generated_at    TIMESTAMPTZ
└── usage_count     INT DEFAULT 0        ← 被使用次数（运营参考）

practice_records（AI 题库练习记录，Module 8）
├── id              UUID PK
├── student_id      UUID FK → users
├── question_id     UUID FK → ai_questions
├── trigger_type    ENUM(module8_free /       ← Module 8 独立练习入口
│                        wrong_q_followup)    ← 错题复盘触发同类题
├── student_answer  JSONB
├── is_correct      BOOLEAN
├── wrong_question_id UUID FK (nullable)  ← 来源错题（触发同类题时有值）
├── practiced_at    TIMESTAMPTZ
└── time_spent_sec  INT
```

---

### 域 7：老师端（班级 / 任务，4 张表）

```
classes（班级）
├── id              UUID PK
├── teacher_id      UUID FK → users
├── institution_id  UUID FK → institutions (nullable)
├── name            VARCHAR
└── created_at      TIMESTAMPTZ

class_students（班级-学生关联）
├── class_id        UUID FK → classes
├── student_id      UUID FK → users
└── joined_at       TIMESTAMPTZ
    [PRIMARY KEY: (class_id, student_id)]

assignments（出卷任务）
├── id              UUID PK
├── teacher_id      UUID FK → users
├── class_id        UUID FK → classes (nullable)
├── title           VARCHAR
├── questions       JSONB                ← AI 生成题目内容
├── due_at          TIMESTAMPTZ
└── status          ENUM(draft / published / closed)

assignment_submissions（学生提交）
├── id              UUID PK
├── assignment_id   UUID FK → assignments
├── student_id      UUID FK → users
├── answers         JSONB
├── score           DECIMAL
└── submitted_at    TIMESTAMPTZ
```

---

### 域 8：用量配额与报告（2 张表）

```
daily_usage（用量配额持久化计数器）
├── id              UUID PK
├── user_id         UUID FK → users
├── usage_type      VARCHAR              ← "ocr_daily" / "practice_daily" /
│                                          "essay_monthly" / "listening_daily" /
│                                          "grade_change_monthly"
├── period          DATE                 ← 自然日（日配额）或月第一天（月配额）
└── count           INT DEFAULT 0
    [UNIQUE: (user_id, usage_type, period)]

说明：Redis 做实时限流（快），daily_usage 做持久存档（准）。
      Redis key 过期后从 DB 重建计数，两者同步写入。

learning_report_snapshots（学情报告快照）
├── id              UUID PK
├── student_id      UUID FK → users
├── report_type     ENUM(weekly / monthly)
├── period_start    DATE                 ← 报告周期开始日
├── period_end      DATE                 ← 报告周期结束日
├── report_data     JSONB                ← 完整报告内容快照（防历史数据漂移）
└── generated_at    TIMESTAMPTZ
    [UNIQUE: (student_id, report_type, period_start)]
```

---

### 域 9：系统配置与通知（2 张表）

```
system_configs（对应 PRD 5.6，所有限额后台可调）
├── id              UUID PK
├── key             VARCHAR UNIQUE       ← "daily_ocr_limit_basic" / "essay_monthly_pro"…
├── value           JSONB                ← 值（数字/字符串/布尔）
├── description     TEXT
├── updated_by      UUID FK → users
└── updated_at      TIMESTAMPTZ

notifications（站内消息中心）
├── id              UUID PK
├── user_id         UUID FK → users
├── type            ENUM(system / membership / assignment / analysis_done / report_ready)
├── title           VARCHAR
├── content         TEXT
├── is_read         BOOLEAN DEFAULT false
└── created_at      TIMESTAMPTZ
```

---

## 完整表清单（34 张）

| 域 | 张数 | 表名 |
|----|------|------|
| 用户与租户 | 8 | users, institutions, students, teachers, relatives, student_relatives, teacher_students, invite_codes |
| 会员与支付 | 3 | memberships, orders, refund_records |
| 错题与 AI 诊断 | 3 | wrong_questions, ocr_tasks, ai_analyses |
| 知识体系 | 5 | knowledge_points, curriculum_units, unit_knowledge_points, curriculum_words, wrong_question_knowledge_points |
| 学习功能 | 5 | vocabulary_words, vocabulary_learning, essays, listening_records, study_checkins |
| AI 题库与练习 | 2 | ai_questions, practice_records |
| 老师端 | 4 | classes, class_students, assignments, assignment_submissions |
| 用量与报告 | 2 | daily_usage, learning_report_snapshots |
| 系统配置与通知 | 2 | system_configs, notifications |

---

## Section 4-6（进行中）

> Section 4：API 设计约定 — 待确认
> Section 5：OCR Pipeline 架构 — 待确认
> Section 6：腾讯云部署架构 — 待确认
