# R8 技术方案:KP → node 主键统一(收口旧 KP 轴)

## 背景

KP-First(R0–R7)把"知识点 → 知识节点(`knowledge_nodes`)"建成新轴,但是**node 轴是叠加**的:
- 单元/词汇实体未动(`curriculum_units`/`vocabulary_words`/`curriculum_words` 仍现役,**不在本期范围**);
- **旧 KP 轴仍承载大量功能**:`knowledge_points`(kp_id/KP名)+ `unit_knowledge_points`(单元↔KP)+
  `student_kp_mastery`(kp_key=KP名字符串 的掌握台账)。诊断/练习/自适应/口语/学情/小程序仍以 **kp_id / kp_key** 为主键。

R8 目标:**把"按 kp_id/kp_key 取数"全部切到 node_id,退役旧 KP 轴三件套**,使知识点只有一套主键(node)。
系统未上线 → 直接切、不做长期双跑桥接(短过渡见下)。

---

## 现状复核(2026-07 重整 —— 以此为准,下方原盘点部分已过时)

自本方案初稿后,多项已顺带完成,R8 剩余面**比原文小很多**:

**已完成(无需再做):**
- 取题载体:`simulated_questions` 主流量已退役(b66a828),练习/模拟考/自适应/自助出卷统一到 `platform_question`(node)。→ **R8.3 基本完成**。
- 端点主键:`curriculum` 的 `/knowledge-points/{node_id}/...`(讲解/单点掌握/单元汇总)、`grammar` 的 `/kp/{kp_id}/...`(kp_id 实为 node_id,直查 `knowledge_nodes`)已是 node。`/kp-mastery/` 读 `student_kp`(node),趋势已改 `answer_log` 重放。→ **R8.2 大半完成**。

**剩余(真正要做,按独立性/价值排序):**
1. **R8.1 退役旧掌握台账 `student_kp_mastery`(本次开发目标,最独立)**
   - 写:`upsert_mastery`(调用方 ai_service / question_service / practice_service / user_paper_service / assignment_service)现**双写**旧台账 + `student_kp`;改为**只写 `student_kp`(node)**。
   - 读:`get_mastery_tree` / `get_mastery_tree_for_teacher`(消费者 diagnosis / learning_plan / teacher / relative,用 correct_count/wrong_count/kp_key/kp_id/kp_description/last_activity_at)→ 改读 `student_kp` join `knowledge_nodes`,口径**等价**(correct=practice_count−wrong_count)。
   - 读:`incentive_service`(已掌握 KP 数)、`institution_service`(班级 top 弱项 by kp_key)→ 改读 `student_kp`。
   - 迁移:删 `student_kp_mastery` + `kp_mastery_snapshots`;删模型;删已无端点调用的旧 `get_kp_trend`(kp_key/快照)。
2. **R8.4/8.5 退役旧 `knowledge_points` / `unit_knowledge_points`(后续,较缠绕)**
   - `curriculum_service.persist_unit` / `curriculum_kp_service` 仍建/用;practice / question / user_paper / speaking 仍按 `knowledge_point_id` 取题实体。需先把这些取数改 node,再删表。范围更大,R8.1 之后单独排。

**等价对拍口径**:R8.1 只换键/换账,不改算法(弱项排序仍按正确率 correct/total,不引入加权掌握度,避免行为漂移)。

---

---

## 一、现状盘点(按 kp_id / kp_key 取数的点)

### A. HTTP 端点
| 端点 | 主键 | 说明 | 内部现状 |
|---|---|---|---|
| `GET /curriculum/knowledge-points/{kp_id}/contents` | kp_id | 讲解 | 已 kp→name→match_kp→node 读 node_resource(仅入参还是 kp_id) |
| `GET /curriculum/knowledge-points/{kp_id}/mastery` | kp_id | 单点掌握 | 读旧台账 `student_kp_mastery`(by kp.name) |
| `GET /curriculum/units/{unit_id}/mastery-summary` | kp.name | 单元掌握汇总 | 读旧台账 |
| `GET /questions/kp/{kp_id}/practice-questions` | kp_id | 练习取题 | by knowledge_point_id |
| `GET /wrong-questions/by-kp/{kp_id}` | kp_id | 按 KP 查错题 | by kp |
| `GET /kp-mastery/` | 返回 kp_key+kp_id | 个人台账 | **已读 student_kp(node)**;kp_id 即 node_id |
| `GET /kp-mastery/trend?kp_key=` | kp_key | 趋势 | 读旧快照台账 |
| `GET /teacher/assignments/suggest-by-kp?kp_key=` | kp_key | 出题建议 | by KP |
| `GET /teacher/sim-questions?kp_id=` | kp_id | 浏览仿真题 | by kp |
| `GET /teacher/students/{id}/kp-mastery` | — | 老师看板 | 读旧台账 |
| `GET /relative/students/{id}/kp-mastery` | — | 家长看板 | 读旧台账 |
| `GET /admin/questions?kp_id=` | kp_id | 仿真题审核筛选 | by kp |

### B. 服务层仍走旧 KP 轴
`diagnosis_service` · `practice_service` · `adaptive_question_service` · `question_service` ·
`speaking_dialogue_service` · `user_paper_service` · `wrong_question_service` ·
`curriculum_kp_service`(桥的消费者) · `curriculum_service`(persist 建 KP)。

### C. 两条掌握账并存(本期核心)
| 账 | 主键 | 写入 | 读取 |
|---|---|---|---|
| `student_kp_mastery`(旧) | kp_key=KP名 | `upsert_mastery` | 诊断 / 学习计划 / 老师 / 家长 / 激励 / 机构 / `get_mastery_tree` |
| `student_kp`(新) | node_id | `mastery_judge.log_answer` + B 步 `upsert_mastery` 补写 | `/kp-mastery` / 个人图谱 |
> B 步已让 `upsert_mastery` **双写**(台账 + 经 node_alias 补 `student_kp`),新账已部分填充——是 R8 的有利起点。

### D. 取题载体两套
旧 `ai_questions`/`simulated_questions`(by knowledge_point_id) ↔ 新 `platform_question`(by node)。
练习/自助已"从 platform_question 有源取材物化"(冷启动回退 AI),但**入口仍 kp_id**。

---

## 二、待确认决策

- **D1 KP 名/简介归属**:退役 `knowledge_points` 后,展示名与 `match_kp` 名字源统一用 `knowledge_nodes.name`(+ `node_alias`);"单元有哪些知识点"由 `unit_node` 提供。`persist_unit` 不再建 KnowledgePoint。✅倾向:是。
- **D2 台账统一**:`upsert_mastery` 改为**只写 `student_kp`(node)**;`get_mastery_tree` 系列改读 `student_kp`;趋势 `trend` 改读 `answer_log` 日聚合(`student_graph_service.node_trend` 已实现)。退役 `student_kp_mastery` + 快照表。
- **D3 取题载体**:练习/自适应/仿真入口改 `node_id`,题源统一 `platform_question`(冷启动回退 AI)。旧 `ai_questions`/`simulated_questions` 是否同期退役,还是仅作答实体保留?(建议:保留作答实体,停止"按 kp_id 取题"入口)
- **D4 兼容窗口**:系统未上线 → **直接替换端点主键(kp_id→node_id)**,不保留旧别名;小程序同步改。(若想灰度→保留 kp_id 别名一版)
- **D5 诊断/自适应聚类**:其"按 KP 聚类弱项/选题"逻辑改为"按 node 聚类",保持算法等价(只换键)。

---

## 三、切换顺序(分步、每步可 commit + 回归)

**R8.0 数据前置(必须先做)**
确保每个在用 KP 都有对应 active node:跑 `scripts/migrate_kp_to_node.py` + 候选审核到位;
否则切 node 后取数为空。产出"未覆盖 KP"清单,人工补 alias/approve。

**R8.1 台账统一到 node(C/D2)**
- `upsert_mastery` 主写 `student_kp`(node_id),停写 `student_kp_mastery`;
- `get_mastery_tree` / `get_mastery_tree_for_teacher` 改读 `student_kp` join `knowledge_nodes`;
- `trend` 改 `node_trend`(answer_log 聚合);
- 回归:诊断 / 学习计划 / 老师 / 家长 / 激励 / 机构 全链。

**R8.2 读端点主键切 node(A)**
逐端点把 `kp_id`→`node_id`、`kp_key`→`node_id`,service 内部按 node:
讲解/单点掌握/单元汇总、练习取题、错题 by-node、teacher suggest/sim/看板、relative 看板、admin 筛选。

**R8.3 取题载体统一(D3)**
练习/自适应/仿真入口 by node,题源 `platform_question`;旧 by-kp_id 取题函数下线。

**R8.4 生成链去桥(D1)**
`persist_unit` 停建 `knowledge_points`/`unit_knowledge_points`,KP 名直接 `match_kp` → `unit_node` 承载;
`curriculum_kp_service` 简化(名字源改 node);`get_kp_contents` 入口随 R8.2 改 node。

**R8.5 退役旧表**
迁移删 `knowledge_points` / `unit_knowledge_points` / `student_kp_mastery`(+ 快照表);护栏同步下调。
> 注:`curriculum_words.knowledge?` 等外键先解;`ai_questions.knowledge_point_id` 若保留作答实体则置空/解 FK。

**R8.6 小程序对接(仓外)**
按下表逐接口切;更新 `docs/对接清单` 与 mock 示例。

---

## 四、小程序接口影响(逐接口)

| 旧(kp_id/kp_key) | 新(node_id) | 前端文件 | 字段变化 |
|---|---|---|---|
| `/curriculum/knowledge-points/{kp_id}/contents` | 复用 `/curriculum/nodes/{node_id}/resources`(已存在) | `curriculum.ts` | 同 R6 资源结构 |
| `/curriculum/knowledge-points/{kp_id}/mastery` | `/student-kp/nodes/{node_id}/mastery`(新增) | `curriculum.ts` | kp_name→node name |
| `/questions/kp/{kp_id}/practice-questions` | `/questions/node/{node_id}/practice-questions` | `questions.ts` | — |
| `/wrong-questions/by-kp/{kp_id}` | `/wrong-questions/by-node/{node_id}` | `wrongQuestions.ts` | tags 已是 node 名 |
| `/kp-mastery/?` + `/trend?kp_key=` | 字段已含 `kp_id`(=node_id);trend 改 `?node_id=` | `kpMastery.ts` | kp_key 仅作展示名 |
| `/teacher/assignments/suggest-by-kp?kp_key=` | `?node_id=` | `teacher.ts` `assignments.ts` | — |
| `/teacher/sim-questions?kp_id=` | `?node_id=` | `teacher.ts` | — |
| `/teacher|relative/students/{id}/kp-mastery` | 同路径,内部切 node;响应 `kp_key`→node 名、`kp_id`→node_id | `teacher.ts` `relative.ts` | 字段语义变 |
| `/examPapers`、`/userPapers` 的 `kp_id` 字段 | → `node_id` | `examPapers.ts` `userPapers.ts` | — |

> 兼容策略(D4):未上线 → 直接替换。小程序与后端**同一批次发**;旧路径删除。

---

## 五、风险 / 回滚 / 验收

- **风险**:R8.0 覆盖不全 → 切 node 后某些 KP 取数为空(诊断/练习空白)。缓解:R8.0 先出"未覆盖 KP"清单并补齐,再切。
- **回滚**:每步独立提交;R8.1–R8.4 纯读写改键,回滚即 revert;R8.5 删表放最后,确认前四步稳定再做。
- **验收**:
  1. 全量回归绿(除既有 7 项无关失败);
  2. 诊断/计划/家长/老师/激励读 `student_kp`(node)结果与旧台账等价对拍;
  3. `git grep KnowledgePoint UnitKnowledgePoint StudentKpMastery` 在 app/ 下归零(仅迁移/历史保留);
  4. 小程序按新表全链跑通(仓外)。

---

## 六、范围外(明确不动)
`curriculum_units` / `vocabulary_words` / `curriculum_words` —— 现役单元/词实体,KP-First 从未替换,R8 不动。
