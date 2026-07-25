# engGramer 生产首发 Runbook

目标:全新服务器上线,DB = 干净结构 + 只灌「内容/缓存/配置」(测试用户/日志一行不进),上线后新建正式 admin。

- 服务器:腾讯云 CVM,IP `124.221.199.214`,用户 `ubuntu`,Ubuntu 24.04,Docker Compose。
- 域名:`api.goodgrammar.top`(后端)、`admin.goodgrammar.top`(后台,待定/可选路径)。
- 数据方案:WIPE 用户/日志、KEEP 内容/缓存(见 `dump_content.sh` 名单)。

---

## 0. 前置(你先做)
1. **DNS A 记录** → `124.221.199.214`:`api.goodgrammar.top`、`admin.goodgrammar.top`(证书签发要求先解析生效)。
2. **生产 `.env`**:照 `.env.production.example` 填真值(POSTGRES_PASSWORD + 各 AI key:DeepSeek/豆包/腾讯 COS·TTS·SOE/智谱…;**豆包 key 不能是 placeholder**,否则 VLM 复核空跑)。稍后放服务器 `/opt/enggramer/.env`。
3. **SSH**:本机能 `ssh ubuntu@124.221.199.214`(买机时关联的密钥)。

## 1. 服务器初始化(一次性)
```bash
ssh ubuntu@124.221.199.214
sudo mkdir -p /opt/enggramer && sudo chown $USER /opt/enggramer
git clone https://github.com/lwjgpt1979-del/EnglishAnalyzer.git /opt/enggramer/repo
# 上传/编辑 .env
vim /opt/enggramer/.env          # 粘贴填好的生产 .env
# 装 docker + certbot + 签证书(按 setup-server.sh;若为 Ubuntu 24.04 apt 同 22.04)
bash /opt/enggramer/repo/deploy/setup-server.sh
```

## 2. 部署代码 + 起服务(含迁移)
```bash
cd /opt/enggramer && bash repo/deploy/deploy.sh
# deploy.sh:拉码 → build 后端镜像 → 起 postgres → alembic upgrade head → compose up → 健康检查
```
此时后端 https://api.goodgrammar.top/health 应 200,但 DB 只有结构、**无内容**。

## 3. 构建初始数据(内容-only)
**本机**(能连开发库):
```bash
cd <项目>/backend && set -a && . ./.env && set +a   # 或确保 docker 开发库在跑
bash ../deploy/dump_content.sh                       # 生成 content_seed.sql(仅内容/缓存)
scp content_seed.sql ubuntu@124.221.199.214:/opt/enggramer/repo/deploy/
```
**服务器**:
```bash
cd /opt/enggramer/repo/deploy
ADMIN_USERNAME=admin ADMIN_PASSWORD='你的强密码' bash build_prod_db.sh content_seed.sql
# 迁移到 head → 灌内容(防重复)→ 建正式 admin → 冒烟计数
```

## 4. 前端 admin / institution(nginx 静态站)
**本机**构建(注入生产 API 地址),再传 dist:
```bash
cd <项目>/frontend/admin && VITE_API_BASE_URL=https://api.goodgrammar.top npm run build
scp -r dist/* ubuntu@124.221.199.214:/opt/enggramer/web/admin/
# institution 同理(如需)→ /opt/enggramer/web/institution/
```
nginx.conf 增加 admin server 块(admin.goodgrammar.top → root /opt/enggramer/web/admin,`try_files $uri /index.html`),reload nginx。

## 5. 冒烟验收
- `curl https://api.goodgrammar.top/health` → 200
- 打开 `https://admin.goodgrammar.top`,用 `admin` + 你设的密码登录 → 能看到词库/教材/配图等内容(证明 KEEP 数据灌成功)。
- admin「LLM 调用清单 / 配图页」等能开(证明配置/缓存在)。

## 6. 日常运维
- **备份**:`deploy/backup_db.sh`(pg_dump gz);建议加 crontab(见 `crontab.md`)。
- **更新上线**:`bash repo/deploy/deploy.sh`(拉码+build+迁移+重启)。
- **前端更新**:本机 build → scp dist → nginx 无需重启(静态直读)。
- **回滚**:后端镜像可按需重打 tag;DB 迁移前有备份(见 `restore_drill.md`)。

## ⚠️ 注意
- `content_seed.sql` 含真实内容数据,**别提交进 git、别外传**;传完可删。
- `build_prod_db.sh` 灌数据幂等(已有内容则跳过),不会重复灌。
- `alembic_version` 不在内容种子里——生产版本由 `upgrade head` 决定(当前 head = `m197_reading_skill`)。
