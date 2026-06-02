# Plan F — 真机联调：后端部署 + 小程序端到端联通

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FastAPI 后端容器化部署到公网服务器（api.goodgrammar.top），配置 HTTPS 与微信合法域名，小程序前端指向生产 API，在微信开发者工具中完成端到端验证（登录 → 上传错题 → AI 分析 → 学情报告）。

**Architecture:** Docker Compose 三服务栈（PostgreSQL + FastAPI/uvicorn + nginx）部署在腾讯云 CVM；nginx 处理 SSL 终止（443）与反向代理（→ 8000）；certbot 签发并自动续签 Let's Encrypt 证书；前端 `.env.production` 指向 `https://api.goodgrammar.top`；COS bucket 用于图片直传，bucket 域名加入微信合法域名白名单。

**Tech Stack:** Docker 24+ · Docker Compose v2 · Ubuntu 22.04 · nginx 1.24 · certbot · Python 3.12 + uvicorn · PostgreSQL 16 · uni-app（微信小程序）· 腾讯云 COS + CVM

---

## ⚠️ 前置清单（执行前手动完成）

在运行任何任务之前，确认已准备：

| 项目 | 来源 |
|------|------|
| 腾讯云 CVM（Ubuntu 22.04）+ 公网 IP | 腾讯云控制台购买 |
| DNS：`api.goodgrammar.top` A 记录 → CVM 公网 IP | DNS 解析管理 |
| 微信小程序 AppID + AppSecret | 微信公众平台 → 开发管理 → 开发设置 |
| 腾讯云 COS bucket 名称 + SecretId + SecretKey | 腾讯云 CAM 控制台 |
| Anthropic API Key | console.anthropic.com |
| 微信支付商户号及证书（可选，MVP 阶段可跳过支付测试） | 微信支付商户平台 |

---

## 文件结构

```
新建文件：
  backend/Dockerfile
  backend/.dockerignore
  deploy/docker-compose.yml
  deploy/nginx.conf
  deploy/setup-server.sh       # 服务器初始化（一次性）
  deploy/deploy.sh             # 拉取新版本并重启（每次发布）
  deploy/.env.production.example  # 生产 .env 模板（提交到 git）
  frontend/miniprogram/.env.production

修改文件：
  frontend/miniprogram/src/manifest.json  # 填入真实 mp-weixin.appid
```

> **安全规则：** `backend/.env` 和服务器上 `/opt/enggramer/.env` 永远不提交到 git。`deploy/.env.production.example` 是模板，不含真实值。

---

### Task 0: Dockerfile + .dockerignore（后端容器化）

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

- [ ] **Step 1: 创建 `backend/Dockerfile`**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

# 系统依赖（psycopg 需要 libpq）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker layer 缓存
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# 再复制应用代码
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 创建 `backend/.dockerignore`**

```
__pycache__
*.pyc
*.pyo
.env
.env.*
!.env.example
.git
.pytest_cache
*.egg-info
tests/
alembic/versions/
```

- [ ] **Step 3: 本地构建验证**

```bash
cd backend
docker build -t enggramer-backend:test .
```

期望输出：`Successfully built <image_id>` 无报错（有 WARNING 关于 alembic.ini 不在 PATH 可忽略）

- [ ] **Step 4: 验证容器可以启动（不连接数据库，预期 500，但进程本身应正常启动）**

```bash
docker run --rm -e DATABASE_URL=postgresql+psycopg://u:p@localhost/db \
  -e ASYNC_DATABASE_URL=postgresql+psycopg_async://u:p@localhost/db \
  -p 8001:8000 enggramer-backend:test &
sleep 3
curl -s http://localhost:8001/health || echo "container started, DB not connected (expected)"
docker stop $(docker ps -q --filter ancestor=enggramer-backend:test) 2>/dev/null || true
```

- [ ] **Step 5: 提交**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "feat(deploy): add Dockerfile and .dockerignore for backend"
```

---

### Task 1: docker-compose.yml（三服务栈）

**Files:**
- Create: `deploy/docker-compose.yml`

- [ ] **Step 1: 创建 `deploy/docker-compose.yml`**

```yaml
# deploy/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    container_name: enggramer_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: enggramer
      POSTGRES_USER: enggramer
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U enggramer -d enggramer"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    image: enggramer-backend:latest
    container_name: enggramer_backend
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - /opt/enggramer/.env        # 生产 .env 在服务器上，不进 git
    networks:
      - internal
      - web
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:1.25-alpine
    container_name: enggramer_nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - /var/www/certbot:/var/www/certbot:ro
    depends_on:
      - backend
    networks:
      - web

volumes:
  pgdata:

networks:
  internal:
    internal: true
  web:
```

- [ ] **Step 2: 验证 compose 语法**

```bash
cd deploy
docker compose config --quiet
echo "syntax OK"
```

期望输出：`syntax OK`（如果没有 .env 文件定义 POSTGRES_PASSWORD 会有警告，属正常，生产时通过 shell 变量或 .env 文件传入）

- [ ] **Step 3: 提交**

```bash
git add deploy/docker-compose.yml
git commit -m "feat(deploy): add docker-compose.yml with postgres + backend + nginx"
```

---

### Task 2: nginx 配置 + HTTPS

**Files:**
- Create: `deploy/nginx.conf`

- [ ] **Step 1: 创建 `deploy/nginx.conf`**

```nginx
# deploy/nginx.conf
# HTTP → HTTPS 重定向 + ACME challenge（certbot）
server {
    listen 80;
    server_name api.goodgrammar.top;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 反向代理
server {
    listen 443 ssl;
    server_name api.goodgrammar.top;

    ssl_certificate     /etc/letsencrypt/live/api.goodgrammar.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.goodgrammar.top/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # 最大请求体（图片 base64 场景，但我们用 COS 直传，后端不接收图片）
    client_max_body_size 10m;

    location / {
        proxy_pass         http://backend:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # AI 分析最长约 30s，留充裕
    }
}
```

- [ ] **Step 2: 验证 nginx 配置格式（本地，需要 nginx 已安装）**

若本地有 nginx：
```bash
nginx -t -c $(pwd)/deploy/nginx.conf 2>&1 || echo "cert files absent locally - expected"
```

SSL 证书路径不存在会报错属正常，只验证语法不报 syntax error 即可。

- [ ] **Step 3: 提交**

```bash
git add deploy/nginx.conf
git commit -m "feat(deploy): add nginx reverse-proxy config with HTTPS"
```

---

### Task 3: 部署脚本（服务器初始化 + 更新）

**Files:**
- Create: `deploy/setup-server.sh`
- Create: `deploy/deploy.sh`
- Create: `deploy/.env.production.example`

- [ ] **Step 1: 创建 `deploy/setup-server.sh`**

此脚本在**全新 Ubuntu 22.04 服务器**上**一次性**执行（`bash setup-server.sh`）。

```bash
#!/usr/bin/env bash
# deploy/setup-server.sh
# 用途：全新 Ubuntu 22.04 服务器初始化（一次性运行）
# 运行方式：ssh root@<SERVER_IP> 'bash -s' < deploy/setup-server.sh
set -euo pipefail

echo "=== [1/6] 更新系统 ==="
apt-get update -y && apt-get upgrade -y

echo "=== [2/6] 安装 Docker ==="
apt-get install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "=== [3/6] 安装 certbot ==="
apt-get install -y certbot

echo "=== [4/6] 创建应用目录 ==="
mkdir -p /opt/enggramer
mkdir -p /var/www/certbot

echo "=== [5/6] 申请 Let's Encrypt 证书 ==="
# 先在 80 端口临时监听（docker 还未起）
certbot certonly --standalone \
  --non-interactive --agree-tos \
  --email admin@goodgrammar.top \
  -d api.goodgrammar.top

echo "=== [6/6] 设置证书自动续签 ==="
echo "0 3 * * 1 certbot renew --quiet && docker exec enggramer_nginx nginx -s reload" \
  | crontab -

echo ""
echo "✅ 服务器初始化完成"
echo "下一步："
echo "  1. 把生产 .env 上传到 /opt/enggramer/.env"
echo "  2. 把 deploy/ 目录上传到服务器"
echo "  3. 运行 deploy.sh 启动服务"
```

- [ ] **Step 2: 创建 `deploy/deploy.sh`**

此脚本在服务器上**每次发版**时执行（`bash deploy.sh`）。

```bash
#!/usr/bin/env bash
# deploy/deploy.sh
# 用途：拉取最新代码，重建镜像，滚动重启服务
# 运行方式：ssh root@<SERVER_IP> 'cd /opt/enggramer && bash deploy.sh'
set -euo pipefail

APP_DIR="/opt/enggramer"
REPO_DIR="$APP_DIR/repo"
GITHUB_REPO="https://github.com/<your-github-user>/engGramer.git"  # ← 替换为真实 repo

echo "=== [1/5] 拉取最新代码 ==="
if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" && git pull origin main
else
  git clone "$GITHUB_REPO" "$REPO_DIR"
fi

echo "=== [2/5] 构建后端镜像 ==="
cd "$REPO_DIR/backend"
docker build -t enggramer-backend:latest .

echo "=== [3/5] 运行数据库迁移 ==="
# 临时跑 alembic upgrade head，使用 postgres 服务
docker run --rm --network enggramer_internal \
  --env-file /opt/enggramer/.env \
  enggramer-backend:latest \
  alembic upgrade head

echo "=== [4/5] 重启服务 ==="
cd "$REPO_DIR/deploy"
# 将生产 POSTGRES_PASSWORD 从 .env 中读取并导出给 docker compose
export POSTGRES_PASSWORD=$(grep '^POSTGRES_PASSWORD=' /opt/enggramer/.env | cut -d= -f2-)
docker compose up -d --remove-orphans

echo "=== [5/5] 健康检查 ==="
sleep 5
curl -sf https://api.goodgrammar.top/health && echo "✅ 部署成功" || echo "❌ 健康检查失败，查看日志：docker compose logs backend"
```

- [ ] **Step 3: 创建 `deploy/.env.production.example`**

```bash
# deploy/.env.production.example
# 用途：生产 .env 模板。复制为 /opt/enggramer/.env，填入真实值。
# 警告：.env 本身永不提交到 git！

# ─── PostgreSQL ───────────────────────────────────────────────
POSTGRES_PASSWORD=请填入高强度随机密码（建议 openssl rand -hex 32）
DATABASE_URL=postgresql+psycopg://enggramer:${POSTGRES_PASSWORD}@postgres:5432/enggramer
ASYNC_DATABASE_URL=postgresql+psycopg_async://enggramer:${POSTGRES_PASSWORD}@postgres:5432/enggramer

# ─── 微信小程序 ────────────────────────────────────────────────
WECHAT_APPID=wx开头的真实 AppID（18位）
WECHAT_APPSECRET=32位十六进制字符串

# ─── JWT ──────────────────────────────────────────────────────
# 生产必须替换，建议 openssl rand -hex 64
JWT_SECRET_KEY=请填入随机64字符串

# ─── Anthropic Claude ─────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...

# ─── 腾讯云 COS ───────────────────────────────────────────────
# 在腾讯云控制台：CAM → API密钥管理
COS_SECRET_ID=AKID_YOUR_COS_SECRET_ID
COS_SECRET_KEY=YOUR_COS_SECRET_KEY
# Bucket 格式：<name>-<appid>，例如 enggramer-prod-1258000001
COS_BUCKET=enggramer-prod-xxxxxxxxxx
COS_REGION=ap-guangzhou
# 注意替换为真实 bucket 名和 appid
COS_BASE_URL=https://enggramer-prod-xxxxxxxxxx.cos.ap-guangzhou.myqcloud.com

# ─── 微信支付 v3（MVP 阶段可先留 placeholder，跳过支付测试）────
WECHAT_PAY_MCH_ID=1600000000
WECHAT_PAY_API_KEY_V3=32字符APIv3密钥（微信支付商户后台设置）
WECHAT_PAY_CERT_SERIAL=证书序列号（apiclient_cert.p12 里查看）
# 多行 PEM 用 \n 连接，整行写入（不换行）
WECHAT_PAY_PRIVATE_KEY_PEM=-----BEGIN PRIVATE KEY-----\n<base64>\n-----END PRIVATE KEY-----
WECHAT_PAY_NOTIFY_URL=https://api.goodgrammar.top/api/v1/webhooks/wx-pay
WECHAT_PAY_SKIP_SIG_VERIFY=false

# ─── 应用 ─────────────────────────────────────────────────────
DEBUG=false
```

- [ ] **Step 4: 给脚本加执行权限并提交**

```bash
chmod +x deploy/setup-server.sh deploy/deploy.sh
git add deploy/setup-server.sh deploy/deploy.sh deploy/.env.production.example
git commit -m "feat(deploy): add server setup and deploy scripts with .env template"
```

---

### Task 4: 前端生产环境配置

**Files:**
- Create: `frontend/miniprogram/.env.production`
- Modify: `frontend/miniprogram/src/manifest.json`（填入真实 appid）

> ⚠️ **执行前必须知道：** 此 Task 需要真实的微信小程序 AppID。登录微信公众平台 → 开发管理 → 开发设置，复制 AppID（格式 `wx` + 16 位）。

- [ ] **Step 1: 创建 `frontend/miniprogram/.env.production`**

```bash
# frontend/miniprogram/.env.production
VITE_API_BASE_URL=https://api.goodgrammar.top
```

- [ ] **Step 2: 修改 `frontend/miniprogram/src/manifest.json`，填入真实 AppID**

将两处空字符串 `""` 替换为真实 appid：
- 第 3 行 `"appid" : ""` → `"appid" : "wx你的AppID"`
- 第 54 行 `"mp-weixin" : { "appid" : ""` → `"appid" : "wx你的AppID"`

```json
{
    "name" : "engGramer",
    "appid" : "wx你的AppID",
    ...
    "mp-weixin" : {
        "appid" : "wx你的AppID",
        "setting" : {
            "urlCheck" : true
        },
        "usingComponents" : true
    },
```

注意：同时将 `"urlCheck": false` 改为 `"urlCheck": true`（生产环境开启域名白名单检查）。

- [ ] **Step 3: 本地构建验证（确认 VITE_API_BASE_URL 注入成功）**

```bash
cd frontend/miniprogram
pnpm build:mp-weixin
grep -r "goodgrammar.top" dist/build/mp-weixin/ | head -3
```

期望：`dist/build/mp-weixin/` 中存在包含 `goodgrammar.top` 的编译产物（例如在某个 .js 文件中）。

- [ ] **Step 4: 提交**

```bash
git add frontend/miniprogram/.env.production frontend/miniprogram/src/manifest.json
git commit -m "feat(frontend): configure production API URL and WeChat AppID"
```

---

### Task 5: 服务器初始化 + 首次部署 + 健康验证

> 此 Task 完全在**服务器端**执行（SSH 登录后）。所有命令在 CVM 上运行。

**Files:** 无新建文件，纯运维操作。

- [ ] **Step 1: DNS 记录验证（本地执行）**

```bash
# 本地执行：确认 api.goodgrammar.top 已指向服务器 IP
nslookup api.goodgrammar.top
# 或
dig api.goodgrammar.top +short
```

期望：输出服务器的公网 IPv4 地址。若 DNS 未生效，等待 TTL 传播后再继续。

- [ ] **Step 2: 服务器初始化（从本地 SSH 执行）**

```bash
# 本地执行：将 setup 脚本传到服务器并运行
scp deploy/setup-server.sh root@<SERVER_IP>:/tmp/setup-server.sh
ssh root@<SERVER_IP> 'bash /tmp/setup-server.sh'
```

期望：最后输出 `✅ 服务器初始化完成`，中间无报错退出。

- [ ] **Step 3: 上传生产 .env（本地执行）**

```bash
# 先在本地复制并填写真实值
cp deploy/.env.production.example /tmp/enggramer-prod.env
# 手动编辑 /tmp/enggramer-prod.env，填入所有真实值...
# 注意：DATABASE_URL 和 ASYNC_DATABASE_URL 中的 ${POSTGRES_PASSWORD} 需要展开，
# 直接写成明文，例如：
# DATABASE_URL=postgresql+psycopg://enggramer:实际密码@postgres:5432/enggramer

# 上传到服务器
scp /tmp/enggramer-prod.env root@<SERVER_IP>:/opt/enggramer/.env
chmod 600 /opt/enggramer/.env   # 限制访问权限（在服务器上执行）

# 确认本地临时文件清理
rm /tmp/enggramer-prod.env
```

- [ ] **Step 4: 服务器上执行首次部署**

```bash
ssh root@<SERVER_IP>
# --- 以下在服务器上执行 ---

# 克隆代码（替换为真实 GitHub repo URL）
git clone https://github.com/<user>/engGramer.git /opt/enggramer/repo

# 构建镜像
cd /opt/enggramer/repo/backend
docker build -t enggramer-backend:latest .

# 运行 DB 迁移（第一次会创建所有表）
# 注意：postgres 服务要先启动，用 docker compose 临时启动
cd /opt/enggramer/repo/deploy
export POSTGRES_PASSWORD=$(grep '^POSTGRES_PASSWORD=' /opt/enggramer/.env | cut -d= -f2-)
docker compose up -d postgres
sleep 10   # 等 postgres 健康

docker run --rm \
  --network deploy_internal \
  --env-file /opt/enggramer/.env \
  enggramer-backend:latest \
  alembic upgrade head

# 启动所有服务
docker compose up -d
```

- [ ] **Step 5: 验证所有容器健康**

```bash
# 在服务器上执行
docker compose ps
```

期望输出（STATUS 列全为 `Up` 或 `healthy`）：
```
NAME                   STATUS
enggramer_postgres     Up (healthy)
enggramer_backend      Up (healthy)
enggramer_nginx        Up
```

- [ ] **Step 6: 验证 HTTPS 端点（本地执行）**

```bash
# 本地执行
curl -s https://api.goodgrammar.top/health
```

期望：`{"status":"ok"}`

```bash
# 验证 SSL 证书有效期
echo | openssl s_client -connect api.goodgrammar.top:443 2>/dev/null | openssl x509 -noout -dates
```

期望：`notAfter` 为大约3个月后（Let's Encrypt 90天有效期）。

- [ ] **Step 7: 验证微信登录 API（本地执行）**

```bash
# 用 curl 模拟一个假 code（预期 40029 错误码，说明 API 通了，微信那边验证了）
curl -s -X POST https://api.goodgrammar.top/api/v1/auth/wx-login \
  -H "Content-Type: application/json" \
  -d '{"code":"test_code_12345"}'
```

期望（不是 502/503，而是业务层错误）：
```json
{"code": 400, "message": "微信登录失败...", "data": null}
```

或任何非网络错误的 JSON 响应，说明后端正常运行并尝试了微信验证。

---

### Task 6: 微信公众平台合法域名配置 + 微信开发者工具 E2E 验证 + D-066 归档

> ⚠️ 此 Task 需要手动操作微信公众平台 + 微信开发者工具，无法自动化。

**Files:**
- Modify: `docs/决策归档.md`（追加 D-066）

- [ ] **Step 1: 配置微信小程序合法域名（手动，约5分钟）**

登录 [微信公众平台](https://mp.weixin.qq.com) → 开发 → 开发管理 → 开发设置 → 服务器域名

添加以下域名：

| 类型 | 域名 |
|------|------|
| **request 合法域名** | `https://api.goodgrammar.top` |
| **request 合法域名** | `https://<COS_BUCKET>.cos.ap-guangzhou.myqcloud.com` |
| **uploadFile 合法域名** | 不需要（我们用 `wx.request` PUT，非 uploadFile） |
| **downloadFile 合法域名** | `https://<COS_BUCKET>.cos.ap-guangzhou.myqcloud.com`（图片预览） |

> 注意：COS bucket 域名格式为 `https://enggramer-prod-xxxxxxxxxx.cos.ap-guangzhou.myqcloud.com`（替换为你的真实 bucket）

- [ ] **Step 2: 微信开发者工具 — 配置并运行**

1. 打开微信开发者工具（需安装：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html）
2. 选择「导入项目」→ 项目目录选 `frontend/miniprogram/dist/build/mp-weixin`（pnpm build:mp-weixin 产物）
3. AppID 填入真实 AppID
4. 确认「不校验合法域名」复选框**不勾选**（要用真实域名测试）

- [ ] **Step 3: E2E 验证清单（微信开发者工具中逐项验证）**

每项验证后在下方记录 ✅ / ❌：

**3.1 微信登录**
- 点击任意需要登录的功能，观察是否弹出微信授权
- 预期：console 无 401 错误，`uni.getStorageSync('access_token')` 有值
- 记录：______

**3.2 错题上传**
- 进入「上传错题」页，选择一张图片（相册或拍照）
- 预期：按钮依次显示「准备上传… → 上传图片中… → 保存错题中… → 上传成功！」
- 预期：自动跳转到错题详情页，看到刚上传的图片
- 记录：______

**3.3 AI 分析**
- 在错题详情页点击「触发 AI 分析」
- 预期：按钮显示「分析中（约3-8秒）…」后变回，下方出现错误类型/知识点/诊断/建议内容
- 记录：______

**3.4 错题列表**
- 切换到「错题本」Tab
- 预期：显示刚上传的错题卡片（图片缩略图 + 日期）
- 记录：______

**3.5 学情报告**
- 切换到「学情」Tab
- 预期：累计错题数 ≥1，已分析 ≥1，显示高频错误类型进度条和 AI 学习建议
- 记录：______

**3.6 掌握状态切换**
- 在错题详情页，拨动「已掌握」开关
- 预期：服务端状态更新，再次进入详情开关保持切换后的状态
- 记录：______

- [ ] **Step 4: 推送当前全量更新**

```bash
git push origin main
```

- [ ] **Step 5: 追加 D-066 到 `docs/决策归档.md`（在 D-065 前插入）**

在文件开头 `---` 后、D-065 块前插入：

```markdown
## D-066｜Plan F 真机联调：后端部署 + 小程序端到端联通

**日期：** 2026-05-27
**背景：** Plan E 前端 MVP 完成后，需要将后端部署到公网并完成真机端到端验证，证明完整业务链路可通。
**结论：**
1. **容器化策略：** 单阶段 Dockerfile（python:3.12-slim），apt 安装 libpq-dev（psycopg 运行依赖），`pyproject.toml -e .` pip install，固定 uvicorn --host 0.0.0.0:8000；`.dockerignore` 排除 .env / tests / .git。
2. **服务栈：** Docker Compose 三服务——postgres:16-alpine（named volume pgdata，健康检查 pg_isready）+ enggramer-backend:latest（env_file=/opt/enggramer/.env，等待 postgres healthy 后启动）+ nginx:1.25-alpine（port 80/443，挂载 nginx.conf + Let's Encrypt cert 目录）；internal/web 双网络隔离 postgres。
3. **HTTPS：** certbot standalone 申请 api.goodgrammar.top 证书（首次在 Docker 启动前独立运行，避免端口冲突）；cron 每周一 03:00 自动 renew + nginx reload。
4. **部署流程：** `setup-server.sh`（一次性）+ `deploy.sh`（每次发版）；alembic upgrade head 在独立容器中运行，确保迁移在后端启动前完成。
5. **生产 .env：** 保存于服务器 `/opt/enggramer/.env`，chmod 600，永不进 git；`deploy/.env.production.example` 作为文档化模板提交。
6. **前端配置：** `.env.production` → `VITE_API_BASE_URL=https://api.goodgrammar.top`；`manifest.json` 填入真实 AppID 并开启 urlCheck；COS bucket 域名加入微信 request + downloadFile 合法域名白名单。
7. **E2E 验证路径：** 登录 → 上传错题（COS PUT）→ AI 分析（Anthropic）→ 学情报告 → 掌握状态切换，共6项。
**影响范围：** backend/Dockerfile、deploy/（5个文件）、frontend/miniprogram/.env.production、manifest.json；服务器侧 /opt/enggramer/.env（不进 git）；已推送 GitHub main 分支。
```

- [ ] **Step 6: 提交归档**

```bash
git add docs/决策归档.md
git commit -m "docs: archive D-066 — Plan F deploy and E2E integration"
git push origin main
```

---

## 常见问题排查

| 症状 | 排查方向 |
|------|----------|
| `502 Bad Gateway` | `docker compose logs backend` 查看启动日志；常见原因：.env 缺字段导致启动崩溃 |
| `curl: SSL certificate problem` | certbot 证书不在 `/etc/letsencrypt/live/api.goodgrammar.top/`；重跑 certbot certonly |
| 微信登录返回 `40029`（invalid code） | 属正常，说明 AppSecret 已生效但 code 无效；真机登录会用真实 code |
| 小程序报 `url not in domain list` | 微信公众平台合法域名白名单未添加 api.goodgrammar.top |
| COS 上传返回 `403` | COS bucket 权限设置问题；检查 SecretId/SecretKey 是否有 cos:PutObject 权限 |
| `alembic upgrade head` 失败 `relation already exists` | 数据库已有旧表；用 `alembic stamp head` 标记当前状态后重试 |
| `docker compose up` 报 `network not found` | 首次 `docker compose up` 会自动创建网络，无需手动处理；若 alembic 步骤用 `--network deploy_internal`，需要先 `docker compose up -d postgres` 创建网络 |
