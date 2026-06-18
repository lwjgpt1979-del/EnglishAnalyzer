# KP-First 新增 API 对接清单(供小程序 / 后台前端)

> KP-First 重构 R0–R7 新增的后端端点汇总。统一前缀 `/api/v1`,响应包 `{code, message, data}`(BaseResponse)。
> **学生端**用学生 JWT(get_current_user);**后台端** `/admin/*` 需 `platform_admin` 角色。
> 旧端点(simulated_questions / kp-mastery / wrong-questions 复习 / curriculum contents)**仍可用**,本次为并行新增;切换节奏由前端把控。

---

## 一、学生端(小程序对接)

### 1. 个人知识图谱(R4)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/student-kp/graph` | `include_all`(bool,默认 false) | 我的知识地图。默认只亮**已练/已错**(弱点优先);`include_all=true` 展开教材全集(含未学)。返回 `{summary{in_scope,practiced,weak,mastered}, items[]}`,item 含 `node_id/name/axis/mastery/practice_count/wrong_count/source_tags/status(mastered|weak|practiced|unlearned)` |
| POST | `/student-kp/enroll` | 无(用用户教材偏好) | 按当前教材偏好显式重同步,把教材应学全集 KP 纳入个人体系。返回 `{enrolled}`。(选教材时已自动纳入,本端点供手动补) |
| GET | `/student-kp/trend` | `node_id`(必), `days`(默认30) | 某知识点掌握趋势(按日 accuracy,数据源 answer_log)。返回 `{node_id, points[{date,accuracy,correct,wrong}]}` |

### 2. 错题中心 / 复习(R3)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/wrong-center/review-queue` | 无 | 今日待复习错题队列(KP-First / wrong_record,SM-2 调度)。返回 `{due_count, items[{id,q_scope,question_id,node_id,review_count,next_review_at}]}` |
| POST | `/wrong-center/review` | `{wrong_record_id, quality(0-5)}` | 提交复习评分 → SM-2 调度下次;达标判掌握。返回 `{status,review_count,next_review_at}` |

### 3. 知识节点学习资源(R6)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/curriculum/nodes/{node_id}/resources` | `resource_type`(可选:lecture/video/example/essay/mindmap) | 某知识节点的**已发布**学习资源。返回 `{total, items[{id,resource_type,dimension,title,content_md,media_url,resource_json,status}]}` |

### 4. 词力通设置(R5 收尾:通用词库 opt-in)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/vocabulary/settings` | 无 | 读设置。新增字段 `include_general_vocab`(bool)、`general_vocab_list_id`(uuid|null) |
| PUT | `/vocabulary/settings` | `{words_per_group,reps_per_group,wrong_carry_threshold, include_general_vocab, general_vocab_list_id}` | 开/关通用词库加选。开后背词新词来源加入通用词库(最低优先,个人体系命中词仍优先) |

> 背词取材优先级(后端 `_ordered_new_words`,前端无需感知):P0 个人体系命中词 > P1 当前学期教材词 > P2 候选(上传/错题) > P3 过往学期 > **P4 通用词库(opt-in)** > 全局兜底。

---

## 二、后台端(admin,已配套后台页)

> 以下端点已在 `frontend/admin` 建有管理页;若用其它后台需对接。

### 5. 候选知识点审核(R0.4)— 页面「🧩 候选知识点审核」
- `GET /admin/kp-candidates?status=pending&axis=&skip=&limit=` 候选队列(高频优先)
- `GET /admin/kp-nodes?axis=&stage=&q=` 归并目标节点搜索
- `POST /admin/kp-candidates/{id}/approve` `{axis,stage?,node_kind?,parent_id?}` 通过建节点
- `POST /admin/kp-candidates/{id}/merge` `{target_node_id}` 归并为别名(治碎片化)
- `POST /admin/kp-candidates/{id}/reject` `{reason}` 驳回

### 6. 平台题(真题/仿真)管理(R2.5)
- `GET /admin/platform-questions?type=&status=&node_id=&skip=&limit=` 平台题查询
- `POST /admin/platform-questions/{real_id}/gen-sim?count=N` 由真题预生成仿真(继承母题 KP)
- `POST /admin/platform-questions/{id}/review` `{approve}` 审核发布

### 7. 教材单元对齐(R1)— 页面「课程内容生成」内
- `GET /admin/curriculum/units/{unit_id}/nodes` 查单元已对齐的知识图谱节点
- `POST /admin/curriculum/units/{unit_id}/extract-kps` 重跑对齐(命中建边/未命中候选)

### 8. 通用词库(R5)— 页面「📒 通用词库」
- `GET /admin/vocab-lists?status=` / `POST /admin/vocab-lists` `{name,exam_level?,source_type?,status?}`
- `GET /admin/vocab-lists/{id}/items` / `POST /admin/vocab-lists/{id}/items` `{items:[{word|word_id,rank?,star?}]}`
- 批量导入用脚本:`python backend/scripts/import_vocab_list.py --name "高考3500" --exam-level senior --file words.json`

### 9. 知识点资源管理(R6)— 页面「🎬 知识点资源」
- `GET /admin/node-resources?status=&node_id=&resource_type=&skip=&limit=` 资源/审核队列
- `POST /admin/node-resources` `{node_id,resource_type,dimension?(lecture需),title?,content_md?,media_url?,resource_json?,status?}` 新增
- `POST /admin/node-resources/{id}/review` `{approve}` 审核发布
- `PUT /admin/node-resources/{id}` `{content_md?,media_url?,title?,resource_json?}` 编辑

---

## 三、迁移/切换建议(给前端)
- 学生端可**渐进切换**:错题复习改读 `/wrong-center/*`;知识地图改读 `/student-kp/graph`;讲解/资源改读 `/curriculum/nodes/{node_id}/resources`(需先有 node_id——可由单元/题的 KP 节点得到)。
- 旧端点未下线,可灰度并行;前端切完后再约后端下线旧表/旧端点(见 [[kp-first-r0-progress]] 遗留项)。
- `node_id` 来源:教材单元 → `GET /admin/curriculum/units/{id}/nodes`(或学生端后续可加单元→节点查询);错题/作答里已带 node_id。
