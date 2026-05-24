# Claude Code Skills 安装经验总结

> 记录在 macOS 上为 Claude Code 安装 gstack 和 Superpowers 两套 skill 框架的完整过程、踩坑点及注意事项。
>
> 更新日期：2026-05-21

---

## 一、gstack（Garry Tan 出品）

**仓库：** https://github.com/garrytan/gstack
**版本：** v1.42.1.0
**安装方式：** git clone + 自带 setup 脚本
**Skill 数量：** 48 个

### 前置依赖：安装 Bun

gstack 的 setup 脚本依赖 **Bun**（JavaScript 运行时），系统里没有会直接报错退出。必须先装 Bun，再跑 setup。

```bash
# 安装 Bun
curl -fsSL https://bun.sh/install | bash

# 让当前终端立即识别 bun 命令（重开终端后自动生效）
export PATH="$HOME/.bun/bin:$PATH"

# 验证
bun --version  # 应输出 1.x.x
```

### 安装步骤

```bash
# 第一步：clone 仓库到 Claude Code skills 目录
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack

# 第二步：运行 setup（确保 Bun 已在 PATH 中）
export PATH="$HOME/.bun/bin:$PATH"
cd ~/.claude/skills/gstack && ./setup
```

> **setup 耗时较长（5~10 分钟）**，主要是下载 Playwright Chromium（~171MB）。保持网络连接，等待完成即可。

### setup 具体做了什么

1. `bun install` 安装 npm 依赖（约 187 秒）
2. 生成 48 个 skill 的 `SKILL.md` 文档
3. 编译 `browse`、`design`、`make-pdf`、`find-browse` 等本地二进制
4. 下载 Playwright Chromium（~171MB，供 `/qa` 浏览器测试使用）
5. 尝试 `brew install coreutils`（macOS 上可能失败，**不影响核心功能**，可忽略）

### 安装后文件位置

```
~/.claude/skills/gstack/                      # 主目录
~/.claude/skills/gstack/VERSION               # 版本号文件
~/.claude/skills/gstack/browse/dist/browse    # 浏览器测试二进制
~/.claude/skills/gstack/design/dist/design    # 设计工具二进制
```

### 核心 Skill 一览（48 个，按工作流分组）

| 阶段 | Skill | 用途 |
|------|-------|------|
| 规划 | `/office-hours` | YC 风格产品需求拷问，生成设计文档 |
| 规划 | `/autoplan` | CEO→设计→工程综合评审，一键生成行动计划 |
| 规划 | `/plan-ceo-review` | 战略范围挑战 |
| 规划 | `/plan-eng-review` | 架构锁定与工程评审 |
| 规划 | `/plan-design-review` | 设计维度审查 |
| 构建 | `/design-consultation` | 设计系统创建 |
| 构建 | `/design-shotgun` | 视觉多方案生成（带品味学习） |
| 构建 | `/design-html` | 从 mockup 生成生产级 HTML |
| 审查 | `/review` | Staff 工程师级代码审查 |
| 审查 | `/investigate` | 根因调试（Root Cause Analysis） |
| 审查 | `/cso` | 安全审计（OWASP Top 10 + STRIDE） |
| 测试 | `/qa` | 真实浏览器测试 + 自动修复 |
| 测试 | `/qa-only` | 仅报告 bug，不修改代码 |
| 发布 | `/ship` | 测试→审查→推送→PR 一键完成 |
| 发布 | `/land-and-deploy` | 合并到生产后验证 |
| 发布 | `/document-release` | 自动更新项目文档 |
| 工具 | `/learn` | 持久化项目记忆（跨 session） |
| 工具 | `/context-save` | 保存当前进度快照 |
| 工具 | `/context-restore` | 恢复上次进度 |
| 工具 | `/investigate` | 系统化 debug 流程 |
| 安全 | `/careful` | 危险操作前警告 |
| 安全 | `/freeze` | 冻结文件，防止意外编辑 |
| 安全 | `/guard` | 守护关键文件 |

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `bun: command not found` | Bun 未装或 PATH 未更新 | `export PATH="$HOME/.bun/bin:$PATH"` |
| `brew install coreutils failed` | macOS brew 警告 | 可忽略，不影响核心功能 |
| Playwright 下载慢或超时 | 网络问题 | 挂 VPN 或重跑 `./setup` |
| skill 没有出现 | setup 未完成 | 确认 `~/.claude/skills/gstack/browse/dist/browse` 文件存在 |

### 更新 gstack

```bash
cd ~/.claude/skills/gstack
git pull
./setup
```

---

## 二、Superpowers（Jesse Vincent 出品）

**仓库：** https://github.com/obra/superpowers
**版本：** v5.1.0（200k+ ⭐）
**安装方式：** Claude Code 原生 plugin 系统
**Skill 数量：** 14 个

### 安装步骤（只需两条命令）

```bash
# 第一步：注册 Superpowers marketplace
claude plugin marketplace add https://github.com/obra/superpowers

# 第二步：安装插件
claude plugin install superpowers
```

安装完成后输出：
```
✔ Successfully installed plugin: superpowers@superpowers-dev (scope: user)
```

> **安装后需重启 Claude Code** 才能加载 skill。

### 安装后文件位置

```
~/.claude/plugins/cache/superpowers-dev/superpowers/5.1.0/skills/
```

### 7 步工作流 + 14 个 Skill

Superpowers 定义了一套 7 步工程方法论，skill 强制串联执行：

| 步骤 | Skill | 作用 |
|------|-------|------|
| 1 | `brainstorming` | 先澄清需求，AI 不会直接写代码 |
| 2 | `using-git-worktrees` | 自动创建隔离的 Git Worktree 环境，保护主分支 |
| 3 | `writing-plans` | 制定精确到文件路径和可验证命令的执行计划 |
| 4 | `subagent-driven-development` | 派子代理按计划逐项执行，支持并行 |
| 5 | `test-driven-development` | 严格 TDD：先写测试（RED）→ 再写代码（GREEN）→ 重构 |
| 6 | `requesting-code-review` | 关键节点强制代码审查 |
| 7 | `finishing-a-development-branch` | 分支收尾、文档更新、交付 |
| 辅助 | `systematic-debugging` | 系统化 debug：假设→验证→根因 |
| 辅助 | `dispatching-parallel-agents` | 并行子代理调度 |
| 辅助 | `executing-plans` | 执行已有计划 |
| 辅助 | `receiving-code-review` | 处理审查反馈 |
| 辅助 | `verification-before-completion` | 完成前验证（不跳过） |
| 辅助 | `writing-skills` | 编写新 skill |
| 入门 | `using-superpowers` | 总览与使用说明（每次对话开始自动触发） |

### 常用管理命令

```bash
# 查看已安装插件
claude plugin list

# 更新到最新版
claude plugin update superpowers

# 临时禁用
claude plugin disable superpowers

# 重新启用
claude plugin enable superpowers

# 卸载
claude plugin uninstall superpowers

# 查看已注册的 marketplace
claude plugin marketplace list
```

---

## 三、两套 Skill 对比

| 维度 | gstack | Superpowers |
|------|--------|-------------|
| 作者 | Garry Tan（YC 总裁） | Jesse Vincent |
| GitHub Stars | 数百 | 200k+ |
| 定位 | 虚拟工程团队（多角色评审） | 工程方法论（7步强制流程） |
| Skill 数量 | 48 个 | 14 个 |
| 安装方式 | `git clone` + `./setup` | `claude plugin install` |
| 前置依赖 | Bun、Playwright Chromium | 无额外依赖 |
| 安装复杂度 | 中（需先装 Bun，setup 耗时长） | 低（两条命令，1 分钟完成） |
| 浏览器测试 | ✅ 内置（`/qa`，基于 Playwright） | ❌ 无 |
| 设计工具 | ✅ 内置（`/design-*` 系列） | ❌ 无 |
| 安全审计 | ✅ 内置（`/cso`） | ❌ 无 |
| TDD 支持 | 部分（`/review` 中包含） | ✅ 完整（独立 skill，强制执行） |
| Git Worktree | 部分 | ✅ 完整（第 2 步强制） |
| 可同时使用 | ✅ | ✅ |
| skill 注册方式 | `~/.claude/skills/` 目录 | Claude Code 原生 plugin 系统 |

### 选哪个？

- **做产品规划、设计评审、浏览器测试** → gstack（`/office-hours`、`/qa`、`/design-*`）
- **日常功能开发、严格工程纪律** → Superpowers（7步流程强制走，不会跳步）
- **两个都要** → 可以同时安装，互不干扰

---

## 四、安装顺序推荐

```bash
# 1. 安装 Bun（gstack 依赖）
curl -fsSL https://bun.sh/install | bash
export PATH="$HOME/.bun/bin:$PATH"

# 2. 安装 gstack
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup
# 等待 setup 完成（约 5~10 分钟）

# 3. 安装 Superpowers
claude plugin marketplace add https://github.com/obra/superpowers
claude plugin install superpowers

# 4. 重启 Claude Code
# skill 全部生效
```

---

*整理自实际安装过程，macOS 环境，2026-05-21*
