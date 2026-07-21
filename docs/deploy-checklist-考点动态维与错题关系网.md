# 部署自检清单 · 考点动态维 + 词中心错题关系网 + 义项消歧 + 考点题报错闭环

> 覆盖迁移 **m181 → m190**。三端(后端 / 小程序 / admin)。上线前逐项核对。

## 一、后端 · 数据库迁移

```bash
cd repo && DATABASE_URL=<prod> alembic upgrade head   # 现为单头,可正常跑
```

本轮新增迁移(依次):

| 迁移 | 建 / 改 |
|---|---|
| m181 | `vocab_word_kp` + `vocab_word_relation`(考点关系图) |
| m182 | `vocab_kp_mcq`(考点扩展测试题) |
| m183 | `student_wrong_relation`(旧「每题选项两两图」·**遗留不再读**) |
| m184 | `vocab_word_relation`:`relation`→VARCHAR(32) + `dim_label` + `sort`(动态维度) |
| m185 | `student_wrong_word`(词中心错题网:词↔错题 主/次角色) |
| m186 | `vocab_kp_mcq.dimension`→VARCHAR(32)(动态维度键超 16) |
| m187 | `vocab_word_sense` + `vocab_word_relation/vocab_kp_mcq/student_wrong_word` 加 `sense_id`(义项消歧) |
| m188 | `vocab_kp_mcq.report_count`(学生「换一题」报错计数) |
| m189 | `vocab_kp_mcq_revision`(AI 修正 / 人工编辑 before/after 记录) |
| **m190** | **merge heads → 单头**(必须;否则 `upgrade head` 报 multiple heads) |

**核对**:`alembic heads` 仅 `m190_merge_heads`;部署后 `alembic current` = m190。

## 二、后端 · LLM & 配置

- **必须配置真实 DeepSeek key**(非 `sk-placeholder`)。本轮全依赖 LLM:
  - 考点生成 `vocab_word_kp` · 考点测试出题 `vocab_kp_mcq` · **考点题AI审校修正 `vocab_kp_mcq_fix`(推理档)**
  - 错题网:选项拆块 `wrong_option_split` · 两两判关系 `wrong_pair_relation` · 义项匹配 `wrong_sense_match`
  - 均已登记 `llm_feature_registry`;admin `/llm-features` 应可见。dev-mock 下这些返回空、AI 自动修正不生效。
- **运营配置**:`system_configs.kp_mcq_report_threshold`(默认 3)——admin「考点题复核」页可改，无需手工建。

## 三、定时任务(crontab · 低峰)

考点题被学生报错(report_count ≥ 阈值)→ **DeepSeek 低峰用推理档批量审校修正**(省钱)。

```cron
# 每晚 01:30(北京时间低峰;DeepSeek 低峰约 00:30–08:30)
30 1 * * *  cd /path/to/backend && DATABASE_URL=<prod> python -m app.tasks.fix_kp_mcqs --limit 200 >> /var/log/enggramer/fix_kp_mcqs.log 2>&1
```

- 已进 **定时任务健康看板**(`task_run` · key=`kp_mcq_autofix`),哑火/失败会告警超管。
- admin「考点题复核」页可对单题**手动「AI 修正」**即时修(不必等低峰)。

## 四、小程序端

```bash
cd frontend/miniprogram && npm run build:mp-weixin   # 上传体验版/正式版
```

**核对**:
- 词力通义关「考点拓展」→ 动态维度**按义项分组**(动词有时态/及物性/语态、名词有可数性/单复数…)。
- 错题精讲页「错题关系网」→ 中心=答案词(圆角卡容中英文);顶部**选项值三色 chip**(蓝正确/红错选/灰其他,空壳缩写不可切);叶子节点**点击不下钻**→跳对应维度 tab。
- 多空/多点选项 → 多个答案 chip 可切;填空手写答案不生成红 chip。
- 考点扩展测试每题有**「换一题」**(报错+换新题)。

## 五、admin 端

```bash
cd frontend/admin && npm run build   # 部署
```

**核对**:侧栏「词汇 / 词力通 → **考点题复核**」；列表分页 + 按 report_count 筛/降序 + 批量删；每题「AI 修正 / 编辑 / 修改记录 / 删除」；顶部阈值配置；弹框三控件（最大化/复原/关闭）。需 `platform_admin` 角色。

## 六、上线后回归

- [ ] 多义词(but)考点分义项、错题命中对应义项、考点测试对上义项
- [ ] 多点选项 → 蓝/红/灰 chip 正确、去重、空壳不可切；填空手写不出红 chip
- [ ] 考点测试「换一题」→ 换新题;报错 ≥ 阈值 → 低峰 cron 修（看 `vocab_kp_mcq_revision`）；admin 手动修即时
- [ ] 叶子节点不下钻、跳维度 tab 看解释

## 七、已知 / 注意

- **存量索引重建**:`student_wrong_word` 在"进错题网时"生成。若线上历史索引需按新拆点/角色逻辑重建，可 `TRUNCATE student_wrong_word`（无 LLM、进页面自动重建）。
- **AI 自动修正**为低峰批量（非即时）：报错达阈值后，到当晚低峰任务才修正。运营要即时可在复核页手动点。
- `student_wrong_relation` / 旧 `wrong_relation_service`（每题两两图）已停用于 UI，表遗留未清（`_wrong_options` 仍被复用）。
