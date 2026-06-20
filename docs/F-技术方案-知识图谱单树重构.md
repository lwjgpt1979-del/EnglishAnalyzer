# F · 技术方案：知识图谱单树重构（去 3 轴 → 分类+知识点+详情枢纽）

> 目标：把"3 轴(知识/能力/题型)"的知识图谱,简化为**一棵"分类 → 知识点"树**;
> 每个知识点点开即枢纽:**详解正文 + 反向关联(教材单元 / 真题 / 仿真)+ 关系边**。
> 取代/收口 E-受控知识树 的多轴模型。

---

## 1. 现状(已确认)

- `knowledge_nodes.axis` 分三轴:**知识 364 / 能力 5 / 题型 8**。
- 能力(听/说/读/写/译)+ 题型(8) = **13 个节点,仅被 13 条 `knowledge_node_aliases` 引用**;
  无任何 `node_resource / platform_question_kp / unit_node / student_kp / wrong_record / vocab_node` 引用 → **删除零连带**。
- 知识轴顶层分类:**词法 / 句法 / 篇章**;层级 轴根 → 板块/词类 → 专题 → 考点。
- 详解:`node_resource(resource_type='lecture')` **286 条**(285 考点 + 1)。
- 反向关联三张表已存在,目前多为空:`unit_node`(教材↔点)、`platform_question_kp`(题↔点)、
  `knowledge_node_relations`(点↔点关系)。
- 知识图谱页(`KnowledgeGraph.vue`)**已有**列:六维完整度(=详解)、引用单元、引用真题;
  但带轴筛选 + 轴切换的树。

## 2. 目标模型

```
知识图谱(单树,全部 axis='knowledge')
└─ 词法 / 句法 / 篇章                ← 顶层「分类」
   └─ 名词 / 动词 / 时态 …            ← 中层「分类」
      └─ 可数名词 / 一般现在时 …      ← 专题
         └─ 考点(叶子=知识点)       ← 每个知识点:详解 + 反向关联 + 关系
```

- **不再有"能力/题型"轴**;知识图谱只承载"语言知识分类→知识点"。
- 听力/口语/阅读/写作/题型 → 不进知识图谱(技能/题型维度另论,不在本图谱)。

## 3. 数据层改动

| 项 | 处理 |
|---|---|
| 能力 5 + 题型 8 节点 | **删除**(连带删其 13 条 alias);迁移 mNN 内做,带存在性保护 |
| `axis` 列 | **保留为残留列,恒为 'knowledge'**(不删,避免动 13 处);新逻辑不再按轴分支 |
| seed `knowledge_tree_seed.json` | 删除 `ability` / `exam` 两段,避免 `--reset` 重新灌入 |
| 关联表 | 不动(`unit_node`/`platform_question_kp`/`knowledge_node_relations` 复用) |

> 取舍:`axis` 列不物理删除——它被 13 个后端文件引用,多数是 `where axis='knowledge'`(删列要全改、风险高)。
> 留作恒定值,新代码不读它;待稳定后另起一刀彻底移除(可选 Phase 2)。

## 4. 知识图谱页重构(`KnowledgeGraph.vue`)

- **去掉**:轴筛选下拉(全部轴/知识/能力/考点)、树的轴切换(TREE_AXES)。
- **保留并强化**:单棵知识分类树(词法/句法/篇章 →…→ 考点),可展开/搜索;
  列表/树节点显示:名称、层级、状态、**详解齐否**、**引用单元数**、**引用真题数**。
- **新增**:点知识点 → **详情抽屉**(见 §5)。

## 5. 知识点详情抽屉(枢纽,全做)

点开一个知识点节点,抽屉分区展示:

1. **详解正文** — `node_resource(lecture)` 的 markdown 渲染(考点的讲解)。
2. **反向关联 · 教材** — `unit_node` 反查:哪些教材单元挂了本点(可跳课程页)。
3. **反向关联 · 真题** — `platform_question_kp` ∩ `type='real'`:挂本点的真题列表(可跳平台真题)。
4. **反向关联 · 仿真** — `platform_question_kp` ∩ `type='sim'`:挂本点的仿真列表。
5. **关系边** — `knowledge_node_relations`:与本点相关的其它知识点(前置/相关等)。

### 后端新增 API
- `GET /admin/knowledge-nodes/{id}/detail` → `{ node, lecture, units[], real_questions[], sim_questions[], relations[] }`
  (一次聚合返回;真题/仿真给 id+题干摘要+所属试卷,可跳转)。

## 6. 受影响处 & 收口

| 受影响 | 处理 |
|---|---|
| 题挂知识点选择器(刚做的 3 轴) | **回退单轴**:只加载知识树,去掉 知识/能力/题型 切换 |
| 「按大题一键挂」 | 技能大题(听力/阅读)将无对应节点可挂 → 仅语法大题有意义(行为不变,UI 文案微调) |
| `AI 建议考点` | 不受影响(本就只在 cf-*/jf-* 考点里选) |
| 13 处 `axis` 引用 | 不动(恒为 knowledge,查询仍正确) |
| `KnowledgeGraph.vue` 轴筛选/切换 | 删除 |

## 7. 分步实施(每步可提交 + 测试)

1. **迁移 mNN**:删除 ability/exam 13 节点 + 13 alias;改 `knowledge_tree_seed.json` 删两段。
2. **后端详情聚合**:`node_detail` service + `/knowledge-nodes/{id}/detail` API + schema。
3. **前端 KG 页**:去轴筛选/切换 → 单树;接详情抽屉(详解 + 反向四区 + 关系)。
4. **题挂点选择器回退单轴**(`PlatformQuestions.vue`)。
5. 回归测试 + 文档收口(更新 E-受控知识树:轴模型废止说明)。

## 8. 回滚

- 迁移 downgrade 重建 ability/exam 13 节点(从 seed)。
- 前端为纯增量/删 UI,回滚即还原组件。
- `axis` 列未删 → 任何环节可安全回退。

## 9. 待你确认点

- ✅ 删能力/题型(只留知识分类) — 已定。
- ✅ 详情抽屉全做(详解+反向+关系) — 已定。
- ❓ "题型/能力"维度以后若仍要(如按题型筛题),走 `platform_question.question_type` 列即可,
  **不再进知识图谱**——确认这样即可,无需单独的题型树。
