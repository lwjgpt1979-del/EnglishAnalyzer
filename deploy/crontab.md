# 服务器定时任务 (crontab) 部署说明

后端离线任务都是 `python -m app.tasks.<name>` 的 CLI，靠服务器 crontab 低峰调用。
每个任务内部走 `task_run_service.run(...)`，执行记录进 `task_run`（后台「定时任务健康看板」可看成功/失败/哑火）。

> 说明:命令需带 `DATABASE_URL`(及各第三方 key)环境;下方 `cd /path/to/backend` 换成实际部署路径,
> `python` 换成部署用的解释器(如 venv / `docker compose exec backend python`)。

## 前置:先跑数据库迁移

新任务/新功能上线前，务必先升级到最新迁移(含配图闭环 m173–m175):

```bash
cd /path/to/backend && alembic upgrade heads
```

- `m173_vocab_image_verify_cache` — 配图 VLM 复核结果缓存(按图 md5,不二次付费)
- `m174_vocab_media_report_count` — 单词「图不对」反馈计数
- `m175_vocab_image_report` — 学生「图不对」投票(去重 + 每人每日限流)

## 配图:存量坏图清理 (VLM 复核重刷)

VLM 复核**已发布**配图,检出「词不达意 / 含文字乱码」的图(含"有 brief 但仍坏"、
后台「重刷劣质配图」按 brief 有无筛选覆盖不到的那类)→ 按新管线(生成前自评→负向约束多图→
VLM 复核选优)重刷,拿不到好图则降级词义卡。

- **游标式**:按 id 顺序从上次位置接着扫,一轮扫完自动归零重扫;
- **不二次付费**:好图按图 md5 缓存命中即跳过,不再调 VLM/出图;
- ⚠️ **需真 t2i 环境**才出真图(dev-mock 只会把坏词降级词义卡)。

建议每晚低峰各跑一次(`--max-scan` 控每次工作量,几晚清完存量后维持巡检):

```cron
# 每晚 03:30 复核一批存量配图(坏图自动重刷/降级)
30 3 * * *  cd /path/to/backend && DATABASE_URL=<prod> python -m app.tasks.reverify_vocab_images --limit 200 --max-scan 2000 >> /var/log/enggramer/reverify_vocab_images.log 2>&1
```

> 运营也可在 admin **配图页 →「复核存量配图(VLM)」** 按钮一键触发(同源逻辑,进度走配图页进度条);
> 二者用其一即可。学生端「图不对·换一张」(投票制)是另一条即时补边角的路。

## 考点题 AI 审校修正(低峰批量)

学生「换一题」= 报错的考点题(report_count++)。报错数 ≥ 阈值的题,由此任务在 **DeepSeek 低峰时段**
用**推理档**批量审校修正(答案唯一/干扰项明确错/无歧义),更省钱。修好即 report_count 归 0、记修改记录。

```cron
# 每晚 01:30(北京时间低峰,DeepSeek 低峰约 00:30–08:30)批量修被报错的考点题
30 1 * * *  cd /path/to/backend && DATABASE_URL=<prod> python -m app.tasks.fix_kp_mcqs --limit 200 >> /var/log/enggramer/fix_kp_mcqs.log 2>&1
```

> 阈值在 admin **「考点题复核」页** 可配(`system_configs.kp_mcq_report_threshold`,默认 3);
> 运营也可在该页对单题**手动点「AI 修正」**即时修(不必等低峰)。

## 考点 AI 审校(报错修正 P6 + 巡检自审 P5·低峰批量)

由此任务在 **DeepSeek 低峰时段**用**推理档**分两步(报错优先):
1) **P6 报错修正**:扫被学生报错达阈值(`report_count ≥ kp_report_threshold`,默认 3、后台「考点复核」页可配)的词,逐词审校报错项、删错/改表述、`report_count` 归 0;
2) **P5 巡检自审**:扫未审校(`vocab_word_kp.reviewed_at` 为空)的词,审其「用法/考法类文本维」考点(及物性/语态/句型/可数性/所有格/-ed-ing/介词辨析/用法/语义侧重/考法),置 `reviewed_at`。

可链维(近义/反义/派生/易混/时态…)已 morph/WordNet/命中词库背书、固定搭配已语料印证,不重审。审校均记 `vocab_word_kp_review`(before/after)。

```cron
# 每晚 02:00(北京时间低峰)先修被报错的考点、再巡检自审未审校词
0 2 * * *  cd /path/to/backend && DATABASE_URL=<prod> python -m app.tasks.review_kp --limit 200 >> /var/log/enggramer/review_kp.log 2>&1
```

> 学生在词力通/错题网点考点「报错」→ `report_count++`;运营也可在 admin **「考点复核」页**对单词**手动 AI 修正**(不必等低峰),或编辑/删除单条考点。阈值在该页可配(`system_configs.kp_report_threshold`)。

## 其它已有离线任务

排期见各任务模块 docstring(`backend/app/tasks/*.py`),例如:

- `backfill_vocab_probes` / `backfill_grammar_probes` — 理解探针离线预生成(每晚低峰)
- `send_weekly_reports` — 家长周报推送
- `send_checkin_reminders` — 打卡提醒
- `send_expiry_alerts` — 会员到期提醒
- `refund_sla_alerts` — 退款 SLA 告警
- `crawl_map_leads` — 地图获客采集
- `run_reach_campaigns` — 存量召回触达
