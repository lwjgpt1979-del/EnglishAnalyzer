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

## 其它已有离线任务

排期见各任务模块 docstring(`backend/app/tasks/*.py`),例如:

- `backfill_vocab_probes` / `backfill_grammar_probes` — 理解探针离线预生成(每晚低峰)
- `send_weekly_reports` — 家长周报推送
- `send_checkin_reminders` — 打卡提醒
- `send_expiry_alerts` — 会员到期提醒
- `refund_sla_alerts` — 退款 SLA 告警
- `crawl_map_leads` — 地图获客采集
- `run_reach_campaigns` — 存量召回触达
