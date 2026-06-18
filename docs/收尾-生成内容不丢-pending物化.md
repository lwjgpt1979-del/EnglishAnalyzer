# 收尾:生成内容不丢失(未命中 KP → pending 暂存 → 候选审核后物化 lecture)

## 背景

内容生成切 node_resource 后,KP-First 受控匹配下**未命中 node 的 KP 其讲解被直接跳过**
(冷启动新 KP 落候选,内容丢失)。决策:**生成时不丢内容** —— 未命中即暂存,候选
approve/merge 出 node 后自动物化为 node_resource lecture。

## 设计

新增轻量暂存表 `pending_kp_content`,按 `(kp_name_norm, dimension)` upsert。
- 暂存键用**归一化 KP 名**(非候选 id):persist_unit 早于候选创建,用 name_norm 解耦时序
- 候选 raw_name 与 persist 的 kp.name 同名 → 同 norm,审核时按 norm 精确取回

### 改动
1. **迁移 m91** `pending_kp_content`(id / kp_name_norm / dimension / content_md / source_unit_id /
   generated_by / created_at / updated_at;UNIQUE(kp_name_norm,dimension);带存在性保护)
2. **模型** d11 `PendingKpContent` + models/__init__ 导出
3. **persist_unit**:KP 未命中 node 时,六维讲解 upsert 进 `pending_kp_content`(不再丢);
   命中则照旧写 node_resource lecture
4. **kp_candidate_service** approve & merge:建/并 node 后(紧接 `_backfill_unit_edges`)调
   `_materialize_pending_content(node_id, norm)` → 取 pending → `upsert_lecture`(status=draft,
   generated_by=ai_full)→ 删除已物化 pending 行
5. **护栏** 105 → 106

## 验收
- persist_unit 遇未命中 KP → pending_kp_content 有六维行(内容不丢)
- 候选 approve/merge → pending 物化为 node_resource lecture(draft)+ pending 行清除 →
  NodeResources 审核发布后学生 get_kp_contents 可读
- 回归不破(除既有 7 项无关失败)
