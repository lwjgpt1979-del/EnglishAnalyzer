# KP-First 新增 API 对接清单(供小程序 / 后台前端)

> KP-First 重构 R0–R7 + 长难句 + 内容退役/pending 后的后端端点汇总。统一前缀 `/api/v1`,
> 响应包 `{code, message, data}`(BaseResponse)。
> **学生端**用学生 JWT(get_current_user);**后台端** `/admin/*` 需 `platform_admin` 角色;
> **家长/老师端**用各自 JWT。
> 学生端每个端点的**请求/响应 JSON 示例**见 [对接清单-学生端Mock示例](对接清单-学生端Mock示例.md)。
> 系统未上线:学生端讲解/错题/掌握读取**已直切 KP-First 新表**(路径多数不变,小程序无感),
> 旧 `/admin/contents` 内容审核端点**已退役**(改由 `/admin/node-resources`)。

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

### 4. 知识点讲解 / 掌握(已切 KP-First,路径不变)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/curriculum/knowledge-points/{kp_id}/contents` | 无 | 某知识点六维讲解。**已直切 node_resource**(旧 kp→名→match_kp→node→已发布 lecture);受单元 paywall。返回 `[{dimension,content_md,audio_url}]`(无命中 node 或无已发布 lecture 时为空) |
| GET | `/curriculum/knowledge-points/{kp_id}/mastery` | 无 | 该知识点掌握概况 |
| GET | `/curriculum/units/{unit_id}/mastery-summary` | 无 | 单元维度掌握汇总 |

### 5. 长难句(L1–L7)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/long-sentences` | `node_id`(可选,句法 node), `limit`(默认50) | 已发布长难句列表(平台共享 + 本人个人域)。返回 `{total, items[{id,text,source_kind,syntax_points[]}]}` |
| GET | `/long-sentences/{ls_id}` | 无 | 解析详情。返回 `{id,text,source_kind, analysis{main_clause,layers[{type,text}],translation,difficulty_points[],syntax_points[]}, nodes[{node_id,name,node_kind}]}`(句法点 node 可跳 §3 资源看讲解) |
| GET | `/long-sentences/{ls_id}/verify-types` | 无 | 该句可用验证题型(后台开放且本期可用)。返回 `{types[]}`(cloze/struct_type/main_clause/translate/span_label/rewrite/read_aloud) |
| GET | `/long-sentences/{ls_id}/verify` | `type`(必) | 取一道验证题(不含答案)。返回 `{type,prompt,options[]}` |
| POST | `/long-sentences/{ls_id}/verify` | `{type, answer}` | 提交验证:判分+回写句法 node+错题收口+达标判掌握。返回 `{correct,correct_answer,mastered_nodes[]}`。read_aloud 的 answer 传发音总分;主观题(translate/rewrite/span_label)AI 评分 |

### 6. 词力通设置(R5 收尾:通用词库 opt-in)
| 方法 | 路径 | 入参 | 用途 |
|---|---|---|---|
| GET | `/vocabulary/settings` | 无 | 读设置。新增字段 `include_general_vocab`(bool)、`general_vocab_list_id`(uuid\|null) |
| PUT | `/vocabulary/settings` | `{words_per_group,reps_per_group,wrong_carry_threshold, include_general_vocab, general_vocab_list_id}` | 开/关通用词库加选。开后背词新词来源加入通用词库(最低优先,个人体系命中词仍优先) |

> 背词取材优先级(后端 `_ordered_new_words`,前端无需感知):P0 个人体系命中词 > P1 当前学期教材词 > P2 候选(上传/错题) > P3 过往学期 > **P4 通用词库(opt-in)** > 全局兜底。

### 7. 错题(已切 KP-First,小程序无需改路径)
> 以下旧路径已**直接切到 wrong_record**(路径/响应形状不变,小程序无感):
- `GET /wrong-questions/review-queue`、`POST /wrong-questions/{wq_id}/review`、
  `PATCH /wrong-questions/{wq_id}/mastered` → 均读写 `wrong_record`(SM-2)。队列 item 的 `id` 即
  wrong_record id,内容由 join uploaded_question 提供,`tags` 为知识节点名。
- 与新 `/wrong-center/*` 等价二选一;小程序保持调旧路径即可获得新表数据。

---

## 二、家长 / 老师端

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/teacher/students/{student_id}/kp-mastery` | 老师查学生知识点掌握(旧台账 get_mastery_tree,诊断/计划共用) |
| GET | `/teacher/students/{student_id}/wrong-questions` | 老师查学生错题 |
| GET | `/relative/students/{student_id}/kp-mastery` | 家长查孩子知识点掌握 |
| GET | `/relative/students/{student_id}/wrong-questions` | 家长查孩子错题 |

> 注:学生自查 `GET /kp-mastery/` 已切**新表 student_kp**(node 维度,弱项在前);`/kp-mastery/trend`
> 仍读快照台账。家长/老师/诊断/计划走旧台账 `get_mastery_tree`(未动)。

---

## 三、后台端(admin,已配套后台页)

### 8. 候选知识点审核(R0.4)— 页面「🧩 候选知识点审核」
- `GET /admin/kp-candidates?status=pending&axis=&skip=&limit=` 候选队列(高频优先)
- `GET /admin/kp-nodes?axis=&stage=&q=` 归并目标节点搜索
- `POST /admin/kp-candidates/{id}/approve` `{axis,stage?,node_kind?,parent_id?}` 通过建节点
  (审核出 node 后**自动回填来源单元 unit_node 边 + 物化暂存讲解 pending_kp_content → node_resource lecture**)
- `POST /admin/kp-candidates/{id}/merge` `{target_node_id}` 归并为别名(治碎片化,同样回填边 + 物化暂存)
- `POST /admin/kp-candidates/{id}/reject` `{reason}` 驳回

### 9. 平台题(真题/仿真)管理(R2.5)
- `GET /admin/platform-questions?type=&status=&node_id=&skip=&limit=` 平台题查询
- `POST /admin/platform-questions/{real_id}/gen-sim?count=N` 由真题预生成仿真(继承母题 KP)
- `POST /admin/platform-questions/{id}/review` `{approve}` 审核发布

### 10. 教材单元对齐 + 内容生成(R1 / 内容退役)— 页面「课程内容生成」内
- `GET /admin/curriculum/units` 单元列表 + 内容完成度(`content_count` 现数 node_resource lecture)
- `POST /admin/curriculum/units/{unit_id}/generate` 生成单元内容。**内容直写 node_resource(lecture,draft)**;
  未命中 node 的 KP 讲解暂存 `pending_kp_content`,候选审核后物化(内容不丢)。旧 knowledge_point_contents 已停写
- `GET /admin/curriculum/units/{unit_id}/nodes` 查单元已对齐的知识图谱节点
- `POST /admin/curriculum/units/{unit_id}/extract-kps` 重跑对齐(命中建边/未命中候选)
- `POST /admin/curriculum/generate-semester`、`/pdf/upload`、`/pdf/{file_id}/generate`、`/pdf/{file_id}/pages` 学期/PDF 批量

### 11. 通用词库(R5)— 页面「📒 通用词库」
- `GET /admin/vocab-lists?status=` / `POST /admin/vocab-lists` `{name,exam_level?,source_type?,status?}`
- `GET /admin/vocab-lists/{id}/items` / `POST /admin/vocab-lists/{id}/items` `{items:[{word|word_id,rank?,star?}]}`
- 批量导入用脚本:`python backend/scripts/import_vocab_list.py --name "高考3500" --exam-level senior --file words.json`

### 12. 知识点资源管理(R6)— 页面「🎬 知识点资源」
> **内容审核统一入口**(旧 `/admin/contents` 已退役):AI 生成的讲解 lecture 也在此审核发布。
- `GET /admin/node-resources?status=&node_id=&resource_type=&skip=&limit=` 资源/审核队列
- `POST /admin/node-resources` `{node_id,resource_type,dimension?(lecture需),title?,content_md?,media_url?,resource_json?,status?}` 新增
- `POST /admin/node-resources/{id}/review` `{approve}` 审核发布
- `PUT /admin/node-resources/{id}` `{content_md?,media_url?,title?,resource_json?}` 编辑

### 13. 长难句管理(L5–L7)— 页面「📐 长难句管理」
- `POST /admin/long-sentences/extract?source=&limit=` 触发抽取。`source`:`config`(默认读 sources 配置)\|`all`\|`platform_real`\|`textbook`(平台 Passage)\|`uploaded`(学生上传题→个人域)。返回 `{created,long_kept,edges,candidates,skipped_done}`
- `GET /admin/long-sentences?status=draft&node_id=&skip=&limit=` 审核队列。返回 `{total, items[{id,text,source_kind,status,syntax_points[]}]}`
- `POST /admin/long-sentences/{id}/review` `{approve}` 通过发布 / 退回
- `GET /admin/long-sentences/config` / `PUT /admin/long-sentences/config` `{sources?,verify_types?,min_words?,required_pass?}` 配置(来源开关 / 验证题型开放 / 长句阈值 / 判掌握净做对数)
- 脚本:`python backend/scripts/extract_long_sentences.py --source all`(独立后台任务)

---

## 四、迁移/切换建议(给前端)
- 学生端读取**已直切新表**,路径基本不变:错题 `/wrong-questions/*`(=wrong_record)或新 `/wrong-center/*`;
  知识地图 `/student-kp/graph`;讲解 `/curriculum/knowledge-points/{kp_id}/contents`(=node_resource lecture)
  或按 node 直读 `/curriculum/nodes/{node_id}/resources`;长难句 `/long-sentences/*`。
- `node_id` 来源:教材单元 → `GET /admin/curriculum/units/{id}/nodes`;长难句详情/错题作答里已带 node_id。
- 内容到达学生的链路:生成 → (命中 node)node_resource lecture / (未命中)pending → 候选审核物化 →
  NodeResources 发布 → 学生 contents/resources 可读。详见 [[kp-first-r0-progress]]。
