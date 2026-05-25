# engGramer Tech Spec — 技术规格书

> 版本：v1.4 | 日期：2026-05-25 | 状态：Section 1-4 已确认，Section 5+ 进行中

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
│  ┌─────────────────────┐  ┌──────────┐  ┌────────────┐  │
│  │      Auth 模块       │  │ 业务路由层 │  │ 后台管理接口│  │
│  │ JWT + 微信OAuth      │  │/api/v1/… │  │ /admin/…  │  │
│  │ + 企业微信OAuth（双绑）│  └──────────┘  └────────────┘  │
│  └─────────────────────┘                               │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │                    Service 层                       │ │
│  │  OCRService │ AIService │ MemberService             │ │
│  │  NotificationService（统一推送路由）                  │ │
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
│              OCR 四层管道（详见 §1.1）                    │
│  预处理 → 版面分析（PaddleLayout）→ 分区OCR → LLM诊断    │
│  ├─ 印刷体：阿里云OCR主 / 百度OCR备                      │
│  └─ 手写体：腾讯云OCR主 / Google Document AI 备          │
├─────────────────────────────────────────────────────────┤
│              其他外部服务                                 │
│  DeepSeek / Claude（LLM 诊断）                           │
│  微信支付（Webhook）                                      │
├─────────────────────────────────────────────────────────┤
│              NotificationService 路由目标（详见 §1.4）    │
│  小程序订阅消息 │ 企业微信推送 │ 站内 WebSocket │ 腾讯云SMS │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              监控与告警层（详见 §1.6）                    │
│  腾讯云监控（CLS 日志 + 云监控）│ 企业微信告警机器人        │
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
| 短信服务 | **腾讯云 SMS** | 同云生态，老师绑定邀请短信的唯一下发渠道 |

---

### 1.1 OCR 四层处理管道

> 来源：PRD § 10.2。OCR 层与 LLM 层必须分开，不可用同一模型包揽。

```
学生上传试卷图片（印刷体题目 + 手写作答混合在同一张图）
       │
       ▼
【第零层：图像预处理】
  倾斜矫正 / 去噪增强 / 分辨率检测
  └── 低质量图自动提示学生重拍，不进入后续流程
       │
       ▼
【第一层：版面分析分区】  ← 必须，不可跳过
  PaddleLayout / DocLayout-YOLO
  将同一张图分割为：
  ├── 印刷体区域（题目正文）
  ├── 手写作答区域（学生答案）
  └── 批改标注区（忽略）
       │
       ▼
【第二层：分区域 OCR 引擎】  各区域用对应引擎
  ├── 印刷体区域
  │     ├── 主选：阿里云OCR 读光高精度版（官方 >99.7%）
  │     └── 备选：百度OCR 通用高精版（官方 >99%，有免费额度）
  └── 手写作答区域
        ├── 主选：腾讯云OCR 手写识别（中文实测 94.7%）
        └── 备选：Google Document AI（英文手写实测 92-95%）
  └── 按坐标融合，输出「题目 + 学生答案」结构化文本
       │
       ▼
【第三层：LLM 错因诊断】
  DeepSeek / Claude（语义理解、错因拆解、学情报告生成）
  └── 诊断置信度低时标注置信度，不输出强结论
```

**OCR 处理约束**：
- 识别置信度低于阈值时，自动高亮提示学生手动确认/修正，禁止静默丢弃
- ARQ 异步任务负责调度整条管道，结果通过 WebSocket 通知前端
- 不使用 DeepSeek 做 OCR（生产环境实测仅 75-80%，与 ≥99% 要求差距过大）

---

### 1.2 API 设计约束（7 条原则）

> 来源：PRD § 10.6。从 MVP 第一天起执行，防止小程序强绑定导致后期改造成本。

| 原则 | 具体要求 |
|------|---------|
| **前后端完全分离** | 所有业务逻辑在后端 API 实现；小程序/Web/App 只调用 API，不含业务逻辑 |
| **统一响应格式** | 所有 API 返回 `{ code, message, data, timestamp }`，无例外 |
| **平台无关用户标识** | 微信 `openid` 不作业务主键；登录后映射为平台 `user_id`，`openid` 仅在 Auth 层使用 |
| **标准 JWT 认证** | `Authorization: Bearer <token>`；微信 `session_key` 不透传业务层 |
| **版本管理** | API 路径含版本号 `/api/v1/...`；迭代通过新版本号隔离，不破坏已发布客户端 |
| **文件上传通用化** | 图片/音频上传返回通用 CDN URL，不绑定微信云存储，未来可无缝迁移存储服务商 |
| **推送渠道抽象** | 通知统一经 `NotificationService` 发出，底层渠道（小程序/企业微信/WebSocket）按用户类型路由，业务代码不直接调用具体渠道 |

---

### 1.3 性能 SLA

> 来源：PRD § 10.4。

| 指标 | 目标值 | 备注 |
|------|--------|------|
| OCR + AI 分析结果返回 | ≤ 60 秒 | 单张标准试卷；超时转异步推送通知 |
| 学情报告生成 | ≤ 30 秒 | |
| 系统可用性 | ≥ 99.5% | 考试季高峰期需弹性扩容（TKE HPA） |
| API P99 响应时间 | ≤ 500 ms | 非 OCR/AI 接口 |

---

### 1.4 NotificationService 推送路由

> 来源：PRD § 10.6 + 功能模块 7。所有推送统一经 `NotificationService`，不直连各渠道。

```
业务逻辑触发通知
       │
       ▼
  NotificationService
       │
       ├──→ 小程序订阅消息（subscribeMessage）  ← C端学生/亲人
       │       └── 离线时可达，需用户授权
       │
       ├──→ 站内 WebSocket                    ← 所有在线用户
       │       └── 实时推送，同步写入 notifications 表
       │
       ├──→ 企业微信推送                      ← 机构老师/机构管理员
       │       └── 主推渠道，无需额外授权
       │
       ├──→ 腾讯云 SMS（短信）               ← 老师绑定邀请专用
       │       └── 向未在平台内的老师手机号发送邀请短信
       │           老师无需事先注册，收到短信后通过链接进入注册/确认流程
       │
       └──→ （P2）App Push                   ← 预留，底层可切换
```

**每条推送同步写入 `notifications` 表**，用户错过实时推送后可在站内消息中心查看历史，不依赖 subscribeMessage 授权。

---

### 1.5 老师双 OAuth 身份关联

> 来源：PRD § 10.6 末节。

老师同时持有两个微信体系身份，共享同一 `user_id`：

| 身份 | 登录入口 | 用途 |
|------|---------|------|
| 普通微信身份 | 小程序 wx.login → openid | 日常操作、学生管理、出卷 |
| 企业微信身份 | 企业微信 OAuth → userid | 接收机构系统通知 |

**关联规则**：
- 两者通过手机号或平台 `user_id` 在认证层自动关联，业务层只看 `user_id`
- P0 阶段：企业微信仅作通知渠道，不单独登录；P1 阶段评估企业微信小程序内嵌版

---

### 1.6 监控与告警架构

> 来源：PRD § 1.4（OCR 报警阈值）+ § 10.4（可用性要求）。

**监控组件**：
- **腾讯云 CLS**：收集 FastAPI / ARQ Worker 结构化日志
- **腾讯云监控（Cloud Monitor）**：CVM/TKE 指标（CPU、内存、Pod 数）
- **自定义业务指标**：OCR 失败率、AI 诊断延迟、支付成功率，通过埋点写入监控

**告警规则（P0 必须上线）**：

| 监控指标 | 报警阈值 | 告警渠道 |
|---------|---------|---------|
| OCR 整体识别失败率 | 滑动 1 小时窗口 > 5% | 企业微信告警机器人 + 技术负责人短信 |
| API P99 响应时间 | 连续 5 分钟 > 2000 ms | 企业微信告警机器人 |
| 系统可用性 | < 99.5%（月度统计） | 技术负责人短信 + 邮件 |
| ARQ 任务积压 | 队列深度 > 500 | 企业微信告警机器人 |
| CVM/Pod CPU | 持续 10 分钟 > 80% | 触发 TKE HPA 自动扩容 |

**故障赔付触发**：平台 CLS 日志可证明核心功能（AI分析/试卷上传/错题管理）连续 ≥ 48 小时不可用时，自动触发赔付流程（见 PRD § 8.4）。

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

**当前（MVP）**：
```
平台（1）→ 机构（N）→ 老师（N）→ 学生（N）→ 亲人（N，最多4位）
```

**扩展预留（分公司启用后）**：
```
平台（1）→ 分公司（N，每家覆盖多个城市）→ 机构（N）→ 老师（N）→ 学生（N）→ 亲人（N）
                    ↑
          通过 city_code 自动归属
          用户/机构 city_code → branch_company_cities → branch_companies
```

分公司层不侵入现有业务逻辑：`users.city_code` 与 `institutions.city_code` 已就位，
启用分公司时只需建 `branch_companies` + `branch_company_cities` 两张表，查询一条 JOIN 即可完成归属反推，无需修改已有表结构。

---

## Section 3：核心数据模型（37 张表）

> 共 10 个业务域，所有表使用 UUID 主键，时间戳字段统一用 TIMESTAMPTZ。
> 域 10 为分公司扩展预留，MVP 阶段建表但不启用业务逻辑；分公司成立时直接填数据即可。

---

### 域 1：用户与租户（8 张表）

```
users（所有角色共用基础表）
├── id                    UUID PK
├── openid                VARCHAR UNIQUE       ← 微信 openid，登录唯一标识
├── phone                 VARCHAR
├── nickname              VARCHAR
├── avatar_url            VARCHAR
├── role                  ENUM(student / teacher / relative /
│                              institution_admin / branch_admin /  ← 分公司管理员（预留）
│                              platform_admin)
├── is_active             BOOLEAN DEFAULT true
├── city_code             VARCHAR              ← 归属城市行政区划代码（如 440100=广州）
│                                                优先级：机构城市 > 认证城市 > 用户自选城市
├── city_source           ENUM(self_selected / ← 注册时用户自行选择（非机构用户主路径）
│                              institution /   ← 加入机构时以机构城市覆盖
│                              cert_verified / ← 老师认证审核核实的学校城市
│                              manual)         ← 平台超管手动修正
├── ip_at_registration    INET                 ← 注册时原始 IP，仅作城市选择器预填推荐，审计留存
├── created_at            TIMESTAMPTZ
└── updated_at            TIMESTAMPTZ

institutions（机构）
├── id              UUID PK
├── name            VARCHAR
├── contact_phone   VARCHAR
├── commission_rate DECIMAL              ← 分成比例（见 PRD 5.8）
├── province_code   VARCHAR NOT NULL     ← 省份行政区划代码（审核时核实）
├── city_code       VARCHAR NOT NULL     ← 城市行政区划代码（审核通过后锁定）
├── address         VARCHAR              ← 详细地址（与营业执照注册地一致）
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
├── id                  UUID PK → users.id
├── institution_id      UUID FK → institutions  ← NULL = C 端认证老师
├── cert_status         ENUM(uncertified / pending / certified / rejected)
├── cert_doc_url        VARCHAR              ← 认证材料 COS 路径
├── subject             VARCHAR              ← 任教学科（英语/数学…，搜索区分度）
└── max_students        INT DEFAULT 50       ← 最大绑定学生数上限，防止无限接单

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
├── bind_type       ENUM(institution_assigned /  ← 机构分配（直接 active，无需确认）
│                        self_bound)             ← 学生自主发起（需老师确认）
├── bind_source     ENUM(sms_invite /             ← 学生输入手机号→系统发短信→老师点链接确认
│                        miniprogram_link /      ← 点击老师分享的小程序链接发起
│                        institution_assigned)   ← 机构后台分配
├── status          ENUM(pending /               ← 等待老师确认（self_bound 初始态）
│                        active /                ← 绑定生效
│                        rejected)              ← 老师拒绝
├── institution_id  UUID FK → institutions (nullable)
├── requested_at    TIMESTAMPTZ                  ← 学生发起申请时间
├── bound_at        TIMESTAMPTZ (nullable)        ← 老师确认时间
└── unbound_at      TIMESTAMPTZ (nullable)
    [UNIQUE: (teacher_id, student_id) WHERE status = 'active']
    [NOTE: institution_assigned 类型由后台直接写入 status='active'，跳过 pending]

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
├── id                       UUID PK
├── order_no                 VARCHAR UNIQUE       ← 业务单号（展示用）
├── payer_id                 UUID FK → users      ← 付款人（可能是亲人）
├── beneficiary_id           UUID FK → users      ← 受益学生
├── order_type               ENUM(new / renew / upgrade)
├── tier                     ENUM(basic / pro / promax)
├── duration_months          INT                  ← 6 / 12 / 24 / 36
├── amount_fen               INT                  ← 实收金额（分）
├── status                   ENUM(pending / paid / refunded / partial_refunded)
├── wx_transaction_id        VARCHAR
├── paid_at                  TIMESTAMPTZ
│
│   ── 分公司财务隔离预留字段（分公司未成立时均为 NULL）──────────────────
├── branch_company_id        UUID FK → branch_companies (nullable)
│                                       ← 下单时快照（city_code→分公司解析后冻结）
│                                         即使后续城市划区调整，历史订单归属不变
├── platform_income_fen      INT (nullable)        ← 平台应得金额快照
├── branch_commission_fen    INT (nullable)        ← 分公司应得金额快照
└── institution_commission_fen INT (nullable)      ← 机构应得金额快照（如有）
    [NOTE: 三方金额在 paid_at 时按当时分成比例计算并冻结，后续比例调整不影响历史单]
└── created_at               TIMESTAMPTZ

refund_records（退款记录）
├── id                    UUID PK
├── order_id              UUID FK → orders
├── amount_fen            INT
├── refund_type           ENUM(standard_7d / prorated / appeal)
├── appeal_no_this_year   INT DEFAULT 0  ← 年度申诉计数（独立计数器，见 PRD 4.5.1）
├── status                ENUM(pending / approved / rejected / completed)
├── reason                TEXT
├── branch_company_id     UUID FK → branch_companies (nullable)
│                                    ← 继承自关联订单，用于分公司退款冲抵结算
└── created_at            TIMESTAMPTZ
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

### 域 10：分公司扩展（预留，3 张表）

> MVP 阶段建表，表内无数据；分公司正式成立时直接填入城市映射即可，无需改表结构。
> 归属反查：`users.city_code` / `institutions.city_code` → `branch_company_cities.city_code` → `branch_companies`

```
branch_companies（分公司）
├── id                UUID PK
├── name              VARCHAR              ← 分公司名称（如「华南区」「西南区」）
├── contact_phone     VARCHAR
├── manager_user_id   UUID FK → users      ← 分公司负责人（role=branch_admin）
├── commission_rate   DECIMAL              ← 平台向分公司的分成比例
│
│   ── 财税法务字段（分公司成立时填入）────────────────────────────────────
├── legal_name        VARCHAR              ← 营业执照法定名称（开票抬头）
├── tax_number        VARCHAR              ← 统一社会信用代码（税号）
├── bank_name         VARCHAR              ← 收款开户行名称
├── bank_account      VARCHAR              ← 收款银行账号（落库前加密，展示时脱敏）
│
├── is_active         BOOLEAN DEFAULT true
└── created_at        TIMESTAMPTZ

branch_company_cities（分公司管辖城市映射，M:N）
├── id                    UUID PK
├── branch_company_id     UUID FK → branch_companies
├── city_code             VARCHAR          ← 城市行政区划代码（对应 users/institutions.city_code）
└── effective_from        DATE             ← 该城市归该分公司管辖的起始日期
    [UNIQUE: (branch_company_id, city_code)]
    [NOTE: 同一城市同一时间只能归属一个分公司]

branch_settlements（分公司周期结算账单）
├── id                        UUID PK
├── branch_company_id         UUID FK → branch_companies
├── period_start              DATE             ← 结算周期开始（通常为月初）
├── period_end                DATE             ← 结算周期结束（通常为月末）
├── gross_revenue_fen         INT              ← 周期内归属该分公司的总收入
├── refund_deduction_fen      INT DEFAULT 0    ← 退款冲抵金额
├── net_revenue_fen           INT              ← 净收入（gross - refund）
├── platform_share_fen        INT              ← 平台应得（按 commission_rate 快照计算）
├── branch_payable_fen        INT              ← 应付分公司净额
├── commission_rate_snapshot  DECIMAL          ← 结算时分成比例快照（防后续改率影响历史）
├── status                    ENUM(draft /     ← 系统自动生成草稿
│                                  confirmed / ← 双方确认
│                                  paid)       ← 已打款
├── confirmed_at              TIMESTAMPTZ (nullable)
├── paid_at                   TIMESTAMPTZ (nullable)
├── note                      TEXT (nullable)  ← 备注（如含争议项说明）
└── created_at                TIMESTAMPTZ
    [UNIQUE: (branch_company_id, period_start, period_end)]
```

**启用分公司后的归属查询（单条 JOIN，零改造）**：
```sql
-- 查询某用户归属哪个分公司
SELECT b.name AS branch_name
FROM branch_companies b
JOIN branch_company_cities bc ON b.id = bc.branch_company_id
WHERE bc.city_code = :user_city_code
  AND bc.effective_from <= CURRENT_DATE
  AND b.is_active = true;
```

**分公司业务分离支持的场景**：
- 分公司管理员（`branch_admin`）可查看其管辖城市内的所有机构、老师、学生数据
- 订单在 `paid_at` 时快照 `branch_company_id` + 三方分成金额，城市划区调整不影响历史订单归属
- 退款记录继承订单的 `branch_company_id`，在周期结算时自动冲抵对应分公司收入
- 系统按月生成 `branch_settlements` 草稿，双方确认后按 `branch_payable_fen` 打款
- 财税字段（`legal_name`、`tax_number`）支持分公司作为独立法人开票报税
- 同一城市可在不同时段归属不同分公司（`effective_from` 支持城市划区调整）

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

## Section 4：API 设计约定

---

### 4.1 基础结构与版本管理

```
Base URL：https://api.enggramer.com/api/v1

路由目录：
/api/v1/
├── auth/                 ← 登录 & Token 刷新
├── users/me              ← 当前登录用户信息
├── upload/               ← COS 预签名上传
├── students/             ← 学生扩展操作
├── teachers/             ← 老师扩展操作
├── relatives/            ← 亲人操作
├── wrong-questions/      ← 错题（核心）
├── ocr-tasks/            ← OCR 任务状态轮询
├── analyses/             ← AI 诊断结果
├── vocabulary/           ← 词力通
├── essays/               ← 作文精修
├── listening/            ← 听力跟读
├── practice/             ← AI 题库练习（Module 8）
├── classes/              ← 班级（老师端）
├── assignments/          ← 出卷任务
├── memberships/          ← 会员状态
├── orders/               ← 订单
├── refunds/              ← 退款
├── reports/              ← 学情报告快照
├── notifications/        ← 站内消息
└── admin/                ← 平台/机构后台（P2 完整 UI）

├── knowledge-points/     ← 知识点树（筛选用）
├── curriculum/           ← 教材单元列表
├── webhooks/             ← 微信支付服务端回调
└── admin/                ← 平台/机构后台

版本策略：URL 带版本号（/v1/）；破坏性变更升 v2，v1 保持 6 个月兼容期。
```

---

### 4.2 认证方案（微信登录 → JWT）

```
流程：
① 小程序调用 wx.login() 拿到 code（有效期 5 分钟）
② POST /api/v1/auth/wx-login { "code": "..." }
③ 后端用 code 换取微信 openid（不持久化 session_key）
④ 按 openid 查或创建 users 记录
⑤ 返回 access_token（JWT，2h 有效）+ refresh_token（30天有效）
⑥ 后续所有请求 Header：Authorization: Bearer <access_token>

JWT Payload：
{
  "sub":            "user_uuid",
  "role":           "student",          ← 角色，用于路由权限
  "institution_id": "uuid | null",      ← 机构 ID，行级隔离用
  "tier":           "pro",              ← 会员档位，减少 DB 查询
  "exp":            1234567890
}

Token 刷新：
POST /api/v1/auth/refresh { "refresh_token": "..." }
→ 返回新的 access_token（refresh_token 不变，滑动续期）
```

---

### 4.3 统一响应格式

**成功响应：**
```json
{
  "code": 0,
  "message": "ok",
  "data": { }
}
```

**列表响应（分页）：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [],
    "pagination": {
      "page":      1,
      "page_size": 20,
      "total":     158,
      "has_next":  true
    }
  }
}
```

**错误响应：**
```json
{
  "code": 1301,
  "message": "今日 OCR 次数已达上限",
  "data": {
    "limit":    10,
    "used":     10,
    "reset_at": "2026-05-25T00:00:00+08:00"
  }
}
```

> `data` 在错误时可选填补充信息（如剩余配额、重置时间），方便前端展示引导文案。

---

### 4.4 错误码规范

| 范围 | 类型 | 常用码 |
|------|------|--------|
| **1000–1099** | 认证/权限 | 1001 未登录或 Token 过期；1002 权限不足；1003 账号已封禁 |
| **1100–1199** | 资源 | 1101 资源不存在；1102 资源已删除 |
| **1200–1299** | 参数 | 1201 参数缺失；1202 参数格式错误；1203 参数值越界 |
| **1300–1399** | 配额限制 | 1301 日 OCR 次数超限；1302 日练习次数超限；1303 月作文次数超限；1304 月变更次数超限；1305 日听力次数超限 |
| **1400–1499** | 会员档位 | 1401 功能需要 Pro；1402 功能需要 ProMax |
| **2000–2099** | 外部服务 | 2001 OCR 识别失败；2002 AI 诊断失败；2003 微信支付失败；2004 COS 上传失败 |
| **3000–3099** | 业务逻辑 | 3001 退款条件不满足；3002 亲人绑定已达上限（4位）；3003 邀请码无效或过期；3004 老师绑定冲突（机构学生不可自主换绑）|
| **5000** | 服务器 | 5000 内部错误（对外不暴露细节，写入日志） |

---

### 4.5 分页约定

```
请求参数（Query String）：
  page       INT  默认 1
  page_size  INT  默认 20，最大 100

示例：
  GET /api/v1/wrong-questions?page=2&page_size=20&type=单选&mastered=false
```

---

### 4.6 核心端点速览

#### 认证
```
POST   /auth/wx-login                  微信登录，返回 JWT
POST   /auth/refresh                   刷新 access_token
DELETE /auth/logout                    登出（使 refresh_token 失效）
POST   /auth/bind-phone                绑定/验证手机号（微信 wx.getPhoneNumber 流程）
                                       Request: { "wx_phone_code": "..." }
                                       → 后端调微信 API 解密，写入 users.phone
POST   /auth/guardian/send-code        向监护人手机号发送授权验证码（< 14 岁注册）
                                       Request: { "guardian_phone": "138xxxx" }
POST   /auth/guardian/verify           监护人验证码核验，通过后激活账号
                                       Request: { "guardian_phone": "138xxxx", "code": "123456" }
```

#### 文件上传（COS 预签名）
```
POST   /upload/sign                    获取 COS 预签名上传 URL

Request：{ "file_type": "image/jpeg", "usage": "wrong_question" }
Response：{
  "upload_url": "https://cos.ap-guangzhou...",   ← 前端直接 PUT 此地址
  "cos_key":    "students/uuid/2026/05/xxx.jpg", ← 上传成功后回传给后端
  "expires_in": 300
}

usage 枚举：wrong_question / essay / listening / cert_doc
```

#### 全局用量查询
```
GET    /users/me/quota                 查询当前用户所有配额剩余

Response：{
  "ocr_daily":            { "used": 3, "limit": 10, "reset_at": "..." },
  "practice_daily":       { "used": 1, "limit": 3,  "reset_at": "..." },
  "essay_monthly":        { "used": 2, "limit": 3,  "reset_at": "..." },
  "listening_daily":      { "used": 5, "limit": 20, "reset_at": "..." },
  "grade_change_monthly": { "used": 1, "limit": 3,  "reset_at": "..." }
}
```

#### 错题（核心链路）
```
POST   /wrong-questions/               上传错题（cos_key）→ 触发 OCR，返回 {id, task_id}
GET    /wrong-questions/               错题列表（支持 type/mastered/knowledge_point 过滤）
GET    /wrong-questions/{id}           错题详情（含 AI 诊断结果）
PATCH  /wrong-questions/{id}/mastered  标记已掌握 / 取消掌握
DELETE /wrong-questions/{id}           删除错题
GET    /ocr-tasks/{task_id}/status     轮询 OCR 状态（pending/processing/completed/failed）
```

#### 词力通
```
GET    /vocabulary/today               今日待复习词 + 新词（按 SM-2 调度）
POST   /vocabulary/{word_id}/review    提交复习结果（quality 0-5），更新 SM-2 状态
GET    /vocabulary/progress            掌握词数、连续打卡天数、今日完成率
GET    /vocabulary/words               词库搜索（按年级/单元/关键字）
```

#### 作文精修
```
POST   /essays/                        提交作文（原文 + 可选 wrong_question_id）→ 触发 AI 精修
GET    /essays/                        历史精修列表
GET    /essays/{id}                    精修详情（各维度评分 + AI 改写内容）
GET    /essays/quota                   当月剩余精修次数（Pro 3次/月上限）
```

#### 听力跟读
```
POST   /listening/submit               上传跟读录音（cos_key）→ 触发评分，返回 task_id
GET    /listening/{id}                 评分结果（score + feedback）
GET    /listening/today-stats          今日已跟读次数 / 剩余配额
```

#### AI 题库练习（Module 8）
```
GET    /practice/questions             拉取练习题（按 knowledge_point/difficulty/type 筛选）
POST   /practice/submit                提交答案，返回正误 + 解析；错题自动归集错题库
GET    /practice/today-stats           今日已练题数 / 剩余配额
```

#### 学情报告
```
GET    /reports/weekly/latest          最新周报快照
GET    /reports/weekly                 历史周报列表（分页）
GET    /reports/monthly/latest         最新月报快照
POST   /reports/generate               手动触发生成（节流：同类型 1h 内限触发 1 次）
POST   /analyses/{id}/feedback         提交 AI 诊断结果反馈（学生/老师均可）
                                       Request: { "content": "该题错误类型识别有误..." }
                                       → 写入反馈队列，不修改当前报告内容
```

#### 老师端
```
GET    /teachers/students              我的学生列表（含学情概况）
GET    /teachers/students/{id}/report  查看指定学生的学情报告
POST   /teachers/certification         提交认证申请（上传材料 cos_key）
GET    /teachers/certification/status  查看当前认证审核进度
GET    /teachers/search                搜索认证老师（辅助路径，非主路径）
                                       ?school=xxx     按学校名模糊搜索
                                       ?name=xxx       按老师姓名模糊搜索
                                       返回：teacher_id / 昵称 / 学科 / 学校 / 头像 / 当前学生数/上限
                                       [注：主绑定路径为短信邀请，此接口仅辅助确认老师信息]
POST   /classes/                       创建班级
POST   /assignments/                   创建出卷任务
PATCH  /assignments/{id}/publish       发布任务给学生
GET    /assignments/{id}/submissions   查看学生提交情况
```

#### 学生-老师绑定
```
-- 主路径：学生发起短信邀请
POST   /students/invite-teacher        学生输入老师手机号，系统向该号码发送邀请短信
                                       body: { phone: "13800138000" }
                                       服务端逻辑：
                                         1. 校验该手机号已达 max_students 上限 → 返回 1301 错误
                                         2. 生成邀请 Token（UUID），存 Redis，TTL 48h
                                         3. 调腾讯云 SMS，发送短信模板：
                                            「[学生昵称] 邀请您成为他的英语老师。
                                              点击确认绑定：[小程序链接?token=xxx]
                                              48小时内有效，如非本人操作请忽略。」
                                         4. 在 teacher_students 写入 status=pending，bind_source=sms_invite
                                         5. 若该手机号尚未注册 → 短信引导注册，注册完成后自动完成绑定

GET    /students/invite-teacher/status  查询当前邀请状态（pending/active/rejected/expired）

DELETE /students/unbind-teacher/{teacher_id}  换绑/解绑（仅 self_bound + active 可操作）

-- 辅助路径：老师分享小程序链接（老师主动拉学生）
POST   /teachers/bind-link             生成专属绑定小程序链接（含 teacher_id + 签名参数）
                                       老师在微信/家长群分享，学生点击后进入确认页
                                       → 链接 7 天有效，过期自动失效
                                       → 学生确认后同样走 bind_source=miniprogram_link

-- 老师侧（处理所有来源的绑定申请）
GET    /teachers/bind-requests         待确认列表（status=pending，含两种来源）
                                       返回：学生昵称 / 头像 / 年级 / 申请时间 / bind_source

POST   /teachers/bind-requests/{id}/accept
                                       接受 → status=active，bound_at=now()
                                       → 通知学生："老师已接受你的绑定申请"

POST   /teachers/bind-requests/{id}/reject
                                       拒绝 → status=rejected
                                       → 通知学生："老师暂未接受绑定申请，可重新邀请"
```

#### 亲人端
```
GET    /relatives/students             我绑定的学生列表
GET    /relatives/students/{id}        学生学情（学情报告 + 打卡记录 + 会员状态）
GET    /relatives/students/{id}/checkins  学生打卡历史（连续天数 + 每日完成情况）
POST   /relatives/bind                 绑定学生（输入邀请码）
DELETE /relatives/bind/{student_id}    解绑学生
POST   /orders/                        为学生代付（payer=亲人，beneficiary=学生）
```

#### 会员与支付
```
GET    /memberships/me                 当前会员状态（tier + expires_at）
POST   /orders/                        创建订单（new/renew/upgrade）
POST   /orders/{id}/pay                发起微信支付，返回 wx.requestPayment 参数
GET    /orders/{id}                    订单详情
POST   /refunds/                       发起退款申请
GET    /refunds/{id}                   退款进度查询
```

#### 通知
```
GET    /notifications/                 通知列表（未读优先，分页）
PATCH  /notifications/{id}/read        标记单条已读
PATCH  /notifications/read-all         全部标记已读
```

#### WebSocket（站内实时通知）
```
WS     /ws?token=<access_token>        建立 WebSocket 连接

服务端推送格式：
{
  "type":    "analysis_done",          ← 事件类型
  "payload": { "wrong_question_id": "uuid", "analysis_id": "uuid" }
}

事件类型：
  analysis_done       AI 诊断完成
  report_ready        学情报告生成完成
  assignment_new      收到新任务（学生）
  membership_expired  会员即将到期（3天前）

连接维护：客户端每 30s 发 ping，服务端回 pong；
          access_token 过期后连接断开，前端用 refresh_token 换新 token 后重连。
```

#### 微信支付回调（Webhook，微信服务器调用）
```
POST   /webhooks/wx-pay                微信支付完成后，微信服务器主动回调

处理逻辑：
  1. 验证微信签名（必须，防伪造）
  2. 幂等检查（wx_transaction_id 是否已处理，防重复）
  3. 更新 orders.status = paid，写入 wx_transaction_id + paid_at
  4. 激活 / 续费 / 升级 memberships 记录
  5. 向受益学生 + 付款亲人推送「购买成功」通知
  6. 返回 {"code": "SUCCESS"} ← 必须，否则微信会持续重试 24h

安全：白名单限制来源 IP（微信服务器 IP 段），其他来源返回 403
```

#### 知识点 & 教材单元（筛选用）
```
GET    /knowledge-points               知识点树列表
  Query: grade=8&textbook=人教版&category=grammar
  Response: 树形结构（parent_id 嵌套），前端缓存 24h

GET    /curriculum/units               教材单元列表
  Query: grade=8&textbook_version=人教版&semester=上
```

#### 学生信息更新
```
PATCH  /students/me                    更新年级 / 教材版本 / 学期
  Request: { "grade": "8", "textbook_ver": "人教版", "semester": "上" }
  → Service 层校验月度变更次数（daily_usage grade_change_monthly）
  → 超限返回 1304，附 reset_at
```

#### 账号注销
```
POST   /users/me/deactivate            发起注销申请（进入 7 天冷静期）
DELETE /users/me/deactivate            取消注销申请（冷静期内有效）
GET    /users/me/deactivate/status     查询注销进度（冷静期剩余天数）
```

#### 机构管理员（P1 最小集，归入 /admin/institutions/me/）
```
POST   /admin/institutions/me/teachers              创建老师子账号
GET    /admin/institutions/me/teachers              机构老师列表 + 额度使用
PATCH  /admin/institutions/me/teachers/{id}/quota   设置老师月度出卷/批改上限

POST   /admin/institutions/me/students              分配学生（手机号 或 批量 Excel）
PATCH  /admin/institutions/me/students/{id}/teacher 调整学生所属老师

GET    /admin/institutions/me/report                机构整体学情汇总报告
GET    /admin/institutions/me/usage                 本月 AI 资源配额使用情况
```

---

### 4.7 其他约定

| 项目 | 约定 |
|------|------|
| HTTP 方法语义 | GET 查询（幂等）；POST 创建；PATCH 局部更新；DELETE 删除；PUT 不用 |
| 时间格式 | 统一 ISO 8601 + 时区：`2026-05-24T10:30:00+08:00` |
| 金额单位 | 统一用**分**（INT），前端展示时 ÷ 100 |
| 空值处理 | 字段不存在时返回 `null`，不省略字段 |
| 文件上传 | 前端直传 COS（预签名 URL），不走 FastAPI 中转，节省带宽 |
| 幂等性 | 支付、退款接口支持幂等 Key（Header: `X-Idempotency-Key`），防重复提交 |
| 限流 | 网关层：100 req/min/用户；OCR/作文/听力额外受 daily_usage 配额约束 |
| CORS | 仅允许微信小程序域名 + 管理后台域名，其他来源一律拒绝 |

---

## Section 5-6（进行中）

> Section 5：OCR Pipeline 异步架构 — 待确认
> Section 6：腾讯云部署架构 — 待确认
