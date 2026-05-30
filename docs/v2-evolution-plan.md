# engGramer V2 演进评估文档

> **状态：** 评估稿，待用户审阅确认后转为正式归档 D-079 并启动 Plan N。
>
> **背景：** 产品方向从 "AI 错题分析工具"（V1）转向 "按教材打包的结构化知识库 + 题库 SaaS"（V2）。本文档划清新数据模型、阶段路线、风险点，让动手前有共识。
>
> **日期：** 2026-05-30
> **决策依据：** 用户 2026-05-30 提出需求变更，6 个关键决策已答完。

---

## 一、V1 vs V2 核心差异

```
V1（已上线 P0）                       V2（新方向）
─────────────────                    ──────────────────
单一产品：学生 AI 错题工具            平台产品：教材知识库 + 题库 + 错题 + 班级
单题上传 → AI 分析                    整卷上传 → AI 拆题逐一归类 → 错题重点标
按月会员 ¥9/19/39                    按学期会员（6 个月单位）
                                     
                                     ✚ 教材深度内容（听/听写/语法/写作）
                                     ✚ 运营预制的真题→仿真题库
                                     ✚ 知识点关联视图（课本+真题+做过的题）
                                     ✚ 教师班级私有真题上传
```

V2 的核心数据资产是 **"教材 → 学期 → 知识点"** 这张知识图谱。所有功能（练习、错题归集、学情、付费）都挂在它上面。

---

## 二、核心数据模型（新增/变更）

### 2.1 教材体系扩展

**现有**：`curriculum_units`（id, textbook_version, grade, semester, unit_no, unit_title）✅ 基本骨架在

**新增表**：

```sql
-- 教材深度内容（每个知识点的四维度内容）
CREATE TABLE knowledge_point_contents (
  id            uuid PK,
  knowledge_point_id  uuid FK,   -- 现有 knowledge_points 表
  dimension     enum('listening','dictation','grammar','writing'),
  content_md    text,            -- AI 解读的 markdown 正文
  audio_url     varchar,         -- 听力/听写场景的 AI 生成音频 URL
  example_json  jsonb,           -- 例句、考点、易错点结构化
  status        enum('draft','reviewing','published','retired'),
  generated_by  enum('ai_full','ai_with_human_review'),
  reviewed_by   uuid FK users,   -- 审核运营 ID
  reviewed_at   timestamptz,
  created_at, updated_at
);

-- 真题试卷（运营 + 老师上传共用）
CREATE TABLE exam_papers (
  id            uuid PK,
  source        enum('official_seed','teacher_upload'),  -- 来源
  uploader_id   uuid FK users,   -- 老师上传时是该老师；运营种子是 null
  class_id      uuid FK classes, -- 老师上传时绑定班级；运营种子是 null（私有/公开标识）
  textbook_version varchar,
  grade         varchar,
  semester      enum('上','下'),
  region        varchar,         -- 地区（如 北京/海淀/2024 春）
  title         varchar,         -- "2024 春 海淀区初二英语期中"
  paper_url     varchar,         -- 试卷原图 / PDF
  ocr_status    enum,            -- 复用现有 OCR 流水线
  status        enum('draft','published','retired'),
  created_at, updated_at
);

-- 真题题目（拆分自试卷）
CREATE TABLE exam_questions (
  id            uuid PK,
  paper_id      uuid FK exam_papers,
  question_no   varchar,         -- "1" / "Ⅱ.3" / "完型 12"
  question_type enum('单选','填空','完型','阅读','写作','听力'),
  stem          text,
  options       jsonb,           -- 单选填 4 项；填空空数组
  answer        text,
  explanation   text,            -- AI 出的解析
  difficulty    smallint,        -- 1-5
  created_at, updated_at
);

-- 真题题目 ↔ 知识点 多对多（题号 + 关联强度）
CREATE TABLE exam_question_knowledge_points (
  exam_question_id  uuid FK,
  knowledge_point_id  uuid FK,
  relevance     smallint default 100,  -- 0-100 关联强度，AI 给分
  PRIMARY KEY (exam_question_id, knowledge_point_id)
);

-- 仿真题（基于真题派生，对外呈现的主要题库）
CREATE TABLE simulated_questions (
  id            uuid PK,
  source_exam_question_id  uuid FK exam_questions,  -- 派生自哪道真题
  knowledge_point_id  uuid FK,
  question_type enum,
  stem, options, answer, explanation, difficulty,
  generation_metadata jsonb,     -- 生成参数、AI provider 等
  status        enum('draft','reviewing','published','retired'),
  created_at, updated_at
);
-- 注：仿真题"X 套"通过 status='published' + 取 N 条按知识点筛选实现
```

### 2.2 上传整卷 + 错题重点标

**现有**：`wrong_questions`（单题）

**V2 改为**：

```sql
-- 学生上传的整卷（用户自己做过的，跟 exam_papers 区分）
CREATE TABLE user_uploaded_papers (
  id            uuid PK,
  student_id    uuid FK users,
  title         varchar,         -- 用户填或自动识别"2024-3-15 数学周测"
  source_image_urls jsonb,       -- 多张图（一份试卷多页）
  ocr_status    enum,
  created_at, updated_at
);

-- 学生卷内每道题（不只错题，所有题都入库 → "解析全部内容"）
-- 替代现有 wrong_questions 的"散题"模型
CREATE TABLE user_paper_questions (
  id                uuid PK,
  user_paper_id     uuid FK user_uploaded_papers,
  question_no       varchar,
  question_type     enum,
  stem, student_answer, correct_answer, explanation,
  is_wrong          boolean,     -- ⭐ 错题重点标识
  matched_exam_question_id  uuid FK exam_questions nullable,  -- 若 AI 匹配上某真题
  created_at
);

-- 题目 ↔ 知识点 关联（无论是否错题）
CREATE TABLE user_paper_question_knowledge_points (
  user_paper_question_id  uuid FK,
  knowledge_point_id      uuid FK,
  PRIMARY KEY (user_paper_question_id, knowledge_point_id)
);
```

**迁移策略**：保留旧 `wrong_questions` 表 + 数据**只读**，新流量走 `user_uploaded_papers / user_paper_questions`。MVP 阶段两套模型并存，老用户的历史错题继续可看。

### 2.3 会员模型重构

**现有**：`memberships`（user_id, tier, started_at, expires_at）+ `orders`（duration_months）

**V2 改为**：

```sql
-- 已购学期（核心）
CREATE TABLE purchased_semesters (
  id            uuid PK,
  user_id       uuid FK users,
  textbook_version varchar,
  grade         varchar,
  semester      enum('上','下'),
  tier          enum('basic','pro','promax'),
  semester_no   smallint,        -- 第几个学期（1 起算，1 学期=6 月）
  started_at    timestamptz,
  expires_at    timestamptz,    -- started_at + 6 个月
  order_id      uuid FK orders,
  created_at
);

-- orders 表加字段
ALTER TABLE orders ADD COLUMN semester_count smallint;
ALTER TABLE orders ADD COLUMN purchased_semesters_json jsonb;
-- 不再用 duration_months（保留兼容旧订单，新订单 NULL）
```

**鉴权变化**：
- 旧逻辑：`membership.tier != 'free' && membership.expires_at > now`
- 新逻辑：访问某教材-年级-学期 的知识点内容时，查 `purchased_semesters` 是否覆盖

### 2.4 用户教材偏好

```sql
-- users 加字段
ALTER TABLE users ADD COLUMN preferred_textbook_version varchar;
ALTER TABLE users ADD COLUMN preferred_grade varchar;
ALTER TABLE users ADD COLUMN preferred_semester enum;
-- 注册时填、首页可改
```

---

## 三、用户旅程（V2）

### 注册新用户
1. 微信登录 → 完善资料（加：选教材版本 / 年级 / 学期）
2. 进入首页 → 看到所选学期的"知识点宫格"
3. 点任一知识点 → 学期详情页 → 三档会员价 → 购买 → 6 个月起算

### 学习
4. 学期详情页内：
   - 浏览课本知识（听 / 听写 / 语法 / 写作）
   - 进入"AI 仿真题"练习（每知识点 X 套）
   - 查看"我做过的相关试卷"（之前上传的卷子按知识点反向索引）

### 上传试卷
5. 上传整卷 → OCR → AI 拆题 + 逐题归类知识点 → 入库
6. 学生选错的题在"错题视图"标红
7. 卷上每题反向关联到知识点 → 增量丰富该用户的"已做题"池

### 教师/亲人
8. 教师上传真题给班级私有用（不进公共题库）
9. 教师按班级查看学生上传的"已做卷子"
10. 亲人付费购买学期给孩子

---

## 四、阶段路线（5 个 Milestone）

### M1：数据模型基础 + 学期会员重构（2-3 周）⭐ 优先

**目标**：把骨架立起来，让后续内容能塞进去。

- 迁移 0007：新表 (`knowledge_point_contents`, `exam_papers`, `exam_questions`, `exam_question_knowledge_points`, `simulated_questions`, `user_uploaded_papers`, `user_paper_questions`, `user_paper_question_knowledge_points`, `purchased_semesters`)
- 迁移 0008：users 加 `preferred_*`、orders 加 `semester_count`
- 重写 `order_service` 计价：按学期 + tier，作废 duration_months 计价表
- 重写 `membership_service`：访问鉴权改查 `purchased_semesters`
- 完善资料 onboarding 加教材选择 UI
- Plan N 输出：M1 详细 Task 列表

### M2：种子数据 + 内容呈现（2 周）

- 写 `seed_curriculum.py` 脚本：用 AI 生成 1-2 个教材版本（人教 PEP 小学 5-6 年级 + 初中 7 年级）的知识点 + 4 维度内容 + 音频
- 内容入库 status='published'
- 前端：首页教材/年级/学期切换器；学期详情页（知识点宫格 + 内容浏览）
- 鉴权：未购买学期只能看一两个免费试读知识点，其它锁定

### M3：仿真题 + 关联视图（2 周）

- 写 `seed_simulated_questions.py`：基于真题（也用 AI 直接出）生成 N 套仿真题入库
- 前端：仿真题练习页（复用现有 practice 框架，数据源换成 `simulated_questions`）
- 知识点详情页：显示"课本内容 / 该知识点的仿真题列表 / 我做过的相关题"三 tab

### M4：整卷上传 + 错题归集（2 周）

- 改 OCR 流水线：从"单题图"扩到"多页试卷图"
- AI 拆题逻辑：识别题号 + 题型 + 拆分
- AI 知识点归类：每题归到 1-N 个知识点
- 前端：上传页改"上传试卷"（多图）；详情页改"试卷视图 + 错题视图（红标）"
- 旧 `wrong_questions` 数据兼容显示（"历史错题"区）

### M5：运营后台 V2（独立项目，4-6 周）

- 独立 Vue/React + Element UI Web 项目
- 真题上传 → AI 触发 → 草稿审核 → 发布
- 知识点内容编辑器
- 仿真题审核
- 用户/订单/学期管理

**M1-M4 不动**，M5 是平行项目。

---

## 五、对已有 P0 的影响

| 已有 | 改动 |
|------|------|
| 学生登录 / 合规 / 注销 / 消息中心 | ✅ 不动 |
| 教师身份 + 班级 + 邀请绑定 | ✅ 不动（M5 后老师上传真题入 exam_papers） |
| 家人邀请 + 代付 | ⚠️ 改：代付金额按学期 |
| 微信小程序码 + SMS 邀请（D-078）| ✅ 不动 |
| 学生上传错题（D-061/D-068）| ⚠️ M4 改为"整卷"逻辑，旧数据只读保留 |
| AI 单题分析（D-061）| ⚠️ M4 改为"逐题归类知识点"为主 |
| 学情报告（D-063）| ⚠️ M3 增"按学期 / 按知识点"维度 |
| AI 仿真题练习（D-070）| ⚠️ M3 改为"读 simulated_questions 表"为主 |
| 教师查学生学情 + 班级综合报告（D-075）| ✅ 不动（M3 后增按学期视角） |
| 旧会员价 ¥9/19/39 月 + 微信支付链路 | ❌ M1 重写计价逻辑；支付链路本身复用 |

---

## 六、风险与遗留

| 风险 | 缓解 |
|------|------|
| **AI 自动归类准确率不足** | 半自动模式：AI 出初稿 + 运营审核（status=draft → published）；前期密集质检 |
| **教材版权** | M2 种子阶段只做"知识点 + 解读"不做"原文照搬"；课本原图不入库 |
| **真题版权** | 运营上传的真题**不对外呈现**（仅作内部归类输入），对外呈现的是仿真题（AI 生成不侵权）；老师上传真题仅班级私有 |
| **小程序提审多教材类目** | "在线教育" 类目下可覆盖；但"K12 学科辅导"近年敏感，文案上突出"学习辅助工具/学情诊断"避开监管线 |
| **学期 6 个月起算 vs 自然学期错位** | 显式告诉用户"购买即开始 6 个月"；学期标签是"教材版本-年级-上/下"，不依赖日历对齐 |
| **新旧数据模型并存复杂度** | M1-M4 阶段两套并存；M5 后可考虑数据迁移工具把旧 wrong_questions 导入 user_paper_questions |
| **运营后台缺位** | M1-M4 用 SQL 种子脚本 + admin API（已有骨架）维持；M5 才补 UI |

---

## 七、立即决策点

读完此文档，需要你决策 3 件事：

1. **M1 是否启动？** 启动则我立即写 Plan N（M1 详细 Task 草案），按 subagent-driven-development 执行 2-3 周。
2. **种子教材选哪一两套？** 建议 **人教 PEP 小学 5 年级 上/下学期** + **人教 PEP 初中 7 年级 上/下学期**（覆盖小学高段 + 初中入门两个核心场景，量也不大）
3. **价格点初步定？** Plan N 计价 service 需要数值。我建议起价：基础 ¥39/学期，Pro ¥79/学期，ProMax ¥159/学期（半年价对标月会员的 3-4 倍，符合"打包卖"的定价心理）

---

## 八、相关归档

- D-071 设计风格（黄油相机风）— 继续沿用
- D-073 合规两项 — 不影响
- D-074 消息中心 — 不影响
- D-078 邀请双通道 — 不影响
- D-079（本文档正式归档版）— 待用户审阅后写入 `docs/决策归档.md`

---

**下一步：** 用户审阅本文档 → 答上面 3 个决策 → 我把决议写入 D-079 归档 + 启动 Plan N（M1）。
