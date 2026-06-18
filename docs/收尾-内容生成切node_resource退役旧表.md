# 收尾:内容生成切 node_resource、退役 knowledge_point_contents

## 背景

学生端讲解 `get_kp_contents` 已只读 `node_resource`(R6 直切),但内容生成 `persist_unit`
仍把 AI 生成的多维讲解写进旧 `knowledge_point_contents` —— **生成内容到不了学生**。
决策(已确认):**只写 node_resource,退役旧表**(不桥接旧数据;系统未上线无存量)。

> 另两项遗留经核实无需改:`/wrong-questions/{id}/mastered`+`/review` **早已切 wrong_record**
> (代码 docstring 明示,记忆条目陈旧);小程序对接在仓外。

## 改动

### 1. 生成切表(核心)
- `persist_unit`:每个 KP 走 `match_kp(name, use_llm=False)` 得 node_id,
  按维度 `upsert_lecture(node_id, dimension, content_md, generated_by='ai_full', status=content_status)`
  写 `node_resource`(lecture);**停写** `KnowledgePointContent`
- 维度仅取 node_resource 六维(listening/vocabulary/grammar/reading/translation/writing),其余跳过
- KP 未命中 node(落候选)→ 跳过该 KP 讲解(extract_unit_nodes 仍记候选,审核合并后可重生)

### 2. 退役旧 admin 内容路径
- 删 admin `/contents` GET / `{id}/review` / PUT 三端点 + `_to_content_item` + 相关 import
- 删 `curriculum_service.list_contents_for_review/review_content/update_content`
- 审核统一走 `NodeResources.vue`(node_resource draft→published)

### 3. 统计重指 node_resource
- `admin_stats_service.get_overview`:`contents_by_status` 改统计 `node_resource`(Overview 卡片不变,反映新表)
- `list_units_with_stats`:content_count 改自 `unit_node`→node 的 node_resource lecture 数

### 4. 前端
- 删 `ContentsReview.vue` + 路由 + 菜单「知识点内容审核」(被 NodeResources 取代)

### 5. 保留
- `KnowledgePointContent` 模型/表保留(退役=停用,不删表/不迁移,避免护栏抖动);表自然空置

## 验收
- persist_unit 生成 → node_resource lecture(draft)→ NodeResources 审核发布 → 学生 get_kp_contents 可读
- 旧 /contents 端点移除(404);Overview/单元统计反映 node_resource
- 回归:删 test_admin_contents、调 curriculum 内容相关断言;余既有 7 项无关失败不变
