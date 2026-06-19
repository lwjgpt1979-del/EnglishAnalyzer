# C 期技术方案 — 教材内容版本控制 + AI/导入对比 + 审核发布

> 状态:**待确认**(本文供拍板,确认后再实现)
> 前置:A 期补全闭环(`369ace5`)、B 期单元级发布(`414c2ae`)已上线。
> 适用:系统未上线,可大胆改表、直接切新流程,不桥接旧行为。

---

## 1. 背景与目标

教材内容(知识点六维讲解)由 AI 生成([curriculum_ai_service.py](../backend/app/services/curriculum_ai_service.py) 调 DeepSeek),
也可人工新增/编辑、未来批量导入。当前**重生成 / 重传 PDF 会直接覆盖旧讲解**
([node_resource_service.py:upsert_lecture](../backend/app/services/node_resource_service.py) 用 `on_conflict_do_update`),
旧内容不留痕、无对比、无法回滚。

要满足你的三条诉求:

1. **AI 生成与导入内容都要有对比 + 审核**;
2. **审核通过后有版本控制**(留版本、可追溯);
3. **重新上传走同样的逻辑**(重传 = 产生新版本,先对比再决定是否替换)。

目标:把"覆盖式写入"改成**"产生待审新版本 → 对比 → 审核通过才替换,旧版归档可回滚"**。

---

## 2. 现状缺口(已核对代码)

| 能力 | 现状 | 缺口 |
|---|---|---|
| 讲解内容写入 | `upsert_lecture` on_conflict 直接覆盖 | ❌ 旧内容丢失 |
| 版本/快照 | `node_resource` 无 version/history 字段 | ❌ 无 |
| 对比 diff | 无 | ❌ 无 |
| 来源标记 | 有 `generated_by`(ai_full/ai_with_human_review/manual/imported) | ✅ 可复用为"来源" |
| 审核发布 | `node_resource.status`(draft→published)+ B 期单元级一键发布 | ✅ 复用 |
| 学生可见闸门 | 只读 `status='published'` | ✅ 不变 |

结论:**来源标记、审核闸门、学生读路径都在**,只缺"版本快照 + 对比 + 不覆盖"。

---

## 3. 数据模型(推荐方案 + 三方案对比)

### 推荐:全量历史版本表 `node_resource_version`(append-only 快照)

`node_resource` 仍作为**"当前生效内容"指针**(学生读路径不变,仍读它的 published 行);
新增版本表存**每一次产出的快照 + 来源 + 审核态**。AI版/导入版只是 `source` 不同的两条版本 → "AI vs 导入对比"天然落在版本对比里,无需第三种结构。

```
node_resource_version
  id              UUID  PK
  resource_id     UUID  FK→node_resource.id    -- 归属的"当前内容"行
  node_id         UUID                          -- 冗余,便于按节点/单元查
  dimension       String(12)                    -- 讲解六维(与 resource 对齐)
  version_no      Int                            -- 该 resource 内自增(1,2,3…)
  content_md      Text
  media_url       String  nullable
  resource_json   JSONB   nullable
  source          String(16)                     -- ai_full | imported | manual | regenerate
  origin_ref      JSONB   nullable               -- 溯源:gen_job_id / pdf file_id / 操作人备注
  status          String(12)                     -- pending | published | archived | rejected
  created_by      UUID    nullable
  created_at      TIMESTAMP
  reviewed_by     UUID    nullable
  reviewed_at     TIMESTAMP nullable
  索引: (resource_id, version_no), (node_id), (status)
```

**状态机**:`pending`(新产出待审) → `published`(当前生效,每 resource 至多 1 条) → `archived`(被新版替换的旧版) / `rejected`(审核驳回)。

### 三方案对比

| 方案 | 优点 | 缺点 | 取舍 |
|---|---|---|---|
| **A 留上一版**(resource 上加 `prev_content_md`) | 改动最小 | 多次重生成只剩最近一版,无完整链;来源对比难表达 | 太弱,不满足"重传同理"的多次场景 |
| **B 全量历史版本表** ✅ 推荐 | 任意两版可对比、可回滚任意版、AI/导入对比天然支持、审计完整 | 多一张表 + 流程改造 | 内容平台标准做法,长期正确 |
| **C 按来源并存**(同维度 AI/导入两行) | 直观并列 | 破坏 `uix_node_resource_identity`(每维一行)、"重传"语义塞不进、回滚链缺失 | 其能力已被 B 的 `source` 字段覆盖 |

> **推荐 B**。下文按 B 展开。

---

## 4. 流程改造

### 4.1 写入:覆盖 → 产生版本(核心)

`upsert_lecture` 改为 `submit_lecture_version(node_id, dimension, content, source, ...)`:

- **该维度无任何内容** → 建 `node_resource`(draft)+ version_no=1。
  - 闸门(见 §7 待确认):全新内容默认可直接 published,或同样进 pending。
- **已有当前内容** → **不动当前行**,插入一条 `node_resource_version(status=pending, source=regenerate/imported)`。
  → 即"重传/重生成产生待审新版,不覆盖线上"。

### 4.2 对比 diff

- 后端给 `GET .../versions/{id}/diff?against=current`,返回 `{base, incoming}` 两份 content_md;
- 前端做**行级文本 diff**(轻量,自写或引 `diff` 库)并排/合并展示。
- "AI版 vs 导入版"对比 = 选两条 pending 版本互 diff(同一接口)。

### 4.3 审核 → 替换 + 归档

审核通过某 pending 版本:

1. 当前 published 版本快照 → `archived`;
2. 该 pending 的内容写入 `node_resource` 当前行(content_md/media_url),`node_resource.status=published`;
3. 该版本 `status=published`,记 `reviewed_by/at`。

驳回:版本 `status=rejected`。学生读路径(读 `node_resource` published)完全不变。

### 4.4 回滚

选任一 `archived` 版本 → 走同一"替换 + 归档"逻辑,把它升为当前。

---

## 5. API(管理端,挂 `/admin`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/curriculum/units/{unit_id}/pending-versions` | 单元下待审新版本汇总(总览面板加"有新版"角标用) |
| GET | `/node-resources/{resource_id}/versions` | 某讲解的版本历史 |
| GET | `/node-resource-versions/{id}/diff?against=current\|<other_id>` | 取两份内容供前端 diff |
| POST | `/node-resource-versions/{id}/approve` | 审核通过 → 替换+归档 |
| POST | `/node-resource-versions/{id}/reject` | 驳回 |
| POST | `/node-resources/{resource_id}/rollback/{version_id}` | 回滚到指定归档版 |

生成/导入接口不新增,只是内部改走 `submit_lecture_version`。

---

## 6. 前端 UI(复用 A 期补全总览页)

- **补全总览面板**每个维度格:除 缺/草稿/已发布,新增**"🆕 有待审新版"** 标记;点击 → 打开 **Diff 抽屉**(左当前/右新版,行级高亮),底部「通过替换 / 驳回」。
- **版本历史**:资源行加「历史」按钮 → 版本列表(版本号/来源/时间/状态),可「查看 diff」「回滚」。
- 单元级:`pending-versions` 有值时,单元行/总览头提示"N 个待审新版"。

---

## 7. 待你确认的决策点

1. **全新内容是否也要审核?**
   推荐:**全新(无旧版)直接 published**(沿用现批量生成体验),**只有覆盖已发布内容的重传/重生成才进 pending + 对比 + 审核**。这样"重传同理"成立,又不拖慢首次铺量。
   (备选:全部一律进 pending 审核——更严,但首次铺 8 单元都要逐条过审。)

2. **diff 粒度**:行级文本 diff(够用、零重依赖)够吗?还是要按六维分块/字符级?推荐行级。

3. **版本快照范围**:先只对 **lecture 六维讲解**(会被重生成的部分)做版本;video/example/essay/mindmap 暂不纳入。是否同意?

4. **保留期**:archived 版本永久留 还是 留最近 N 版?推荐永久留(数据量小:文本)。

---

## 8. 实现分期(确认后)

- **C1 数据层 + 不覆盖**:建表 + 迁移 + `submit_lecture_version` 替换 `upsert_lecture`;生成/导入改走它(重传→pending)。含 service 测试。
- **C2 对比 + 审核**:版本/ diff / approve / reject API + 补全总览"有新版"标记 + Diff 抽屉。
- **C3 历史 + 回滚**:版本历史列表 + rollback API + UI。

每期独立可提交、可测试、可上预览验证。

---

## 9. 风险

- `persist_unit` 当前对全新语义批量生成直接 published;改造需保留"首铺直发、重传进审"的分流(见 §7.1)。
- 版本表与 `node_resource` 的 published 一致性:审核替换需在同一事务里完成"归档旧 + 升级新 + 同步 node_resource"。
