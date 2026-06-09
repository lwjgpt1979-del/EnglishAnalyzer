# V2 M29 Spec：微信订阅消息真实接入（D-108 完整实现）

**日期**：2026-06-09  
**关联**：D-108（打卡提醒），上线前清单 #8  
**状态**：设计中

---

## 一、背景

`wechat_subscribe_service.send_checkin_reminder` 的生产分支目前是 `raise NotImplementedError`。  
前端完全没有 `requestSubscribeMessage` 授权入口，用户无法订阅消息。  
本功能是上线前最后一个 ⚠️ 代码缺口。

---

## 二、微信订阅消息流程

```
1. 小程序前端：wx.requestSubscribeMessage({ tmplIds: [TEMPLATE_ID] })
   → 用户点"允许" → 获得一次性订阅授权
2. 后端 cron（每晚 20:00）：
   a. get_access_token()  → 调 /cgi-bin/token?appid=&secret= 获 access_token（缓存 7000s）
   b. 调 /cgi-bin/message/subscribe/send → 携带 openid + template_id + data
3. 消息到达用户微信"服务通知"
```

---

## 三、后端实现

### 3.1 access_token 缓存

微信 access_token 有效期 7200s，高频调用会超限。用模块级变量缓存：

```python
_access_token_cache: dict = {"token": "", "expires_at": 0}

async def _get_access_token() -> str:
    import time, httpx
    now = time.time()
    if _access_token_cache["expires_at"] > now + 60:
        return _access_token_cache["token"]
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": settings.wechat_appid, "secret": settings.wechat_appsecret}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=10)
    data = r.json()
    if "access_token" not in data:
        raise AppError(502, f"微信 access_token 获取失败：{data}")
    _access_token_cache["token"] = data["access_token"]
    _access_token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return _access_token_cache["token"]
```

### 3.2 send_checkin_reminder 真实实现

```python
async def send_checkin_reminder(*, openid: str, streak_days: int) -> bool:
    if _is_dev():
        logger.info("[WX SUBSCRIBE DEV MOCK] ...")
        return True
    return await _send_real_subscribe_message(openid=openid, streak_days=streak_days)

async def _send_real_subscribe_message(*, openid: str, streak_days: int) -> bool:
    token = await _get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"
    payload = {
        "touser": openid,
        "template_id": settings.wechat_subscribe_template_checkin,
        "data": {
            "thing1": {"value": f"已连续打卡 {streak_days} 天"},
            "time2": {"value": "今天"},
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, timeout=10)
    result = r.json()
    if result.get("errcode", 0) != 0:
        logger.warning("[WX SUBSCRIBE] 发送失败 errcode=%s errmsg=%s", result.get("errcode"), result.get("errmsg"))
        return False
    return True
```

> **模板字段**：`thing1` + `time2` 是最通用的打卡提醒模板字段名。用户填模板时需对应配置。

### 3.3 Config 新增字段

无需新增（复用 `wechat_appid`/`wechat_appsecret`/`wechat_subscribe_template_checkin`）。

---

## 四、前端实现

### 4.1 requestSubscribeMessage 时机

在「词力通」完成页（`pages/vocabulary/index.vue` phase==='done'）打卡完成后弹授权：

```typescript
async function requestSubscribePermission() {
  const tmplIds = [store.subscribeTemplateId || 'placeholder']
  if (tmplIds[0] === 'placeholder') return  // dev 模式不弹
  try {
    await new Promise<void>((resolve, reject) => {
      uni.requestSubscribeMessage({
        tmplIds,
        success(res) {
          // res[tmplId] === 'accept' | 'reject' | 'ban'
          resolve()
        },
        fail: reject,
      })
    })
  } catch (e) {
    // 用户拒绝或不支持，静默忽略
  }
}
```

### 4.2 模板 ID 配置

`src/config.ts`（或 `.env`）新增：
```typescript
export const WX_SUBSCRIBE_TEMPLATE_CHECKIN = import.meta.env.VITE_WX_SUBSCRIBE_TEMPLATE_CHECKIN || ''
```

在 `uni-app` 中通过 `process.env` 或 `uni.getAccountInfoSync()` 在 release 版本传入。  
**MVP 方案**：直接在 `vocabulary/index.vue` hardcode template_id，生产填真实值。

---

## 五、测试策略

### 5.1 后端单元测试（mock httpx）

- `test_get_access_token_calls_wechat_api`：验证调用正确 URL + 参数
- `test_get_access_token_caches_result`：缓存命中不重复请求
- `test_send_real_subscribe_message_success`：errcode=0 返回 True
- `test_send_real_subscribe_message_fail`：errcode≠0 返回 False（不抛错，打卡提醒非关键路径）
- `test_send_checkin_reminder_dev_mode`：placeholder provider 不调 httpx

### 5.2 前端

TypeScript 编译通过（tsc --noEmit）

---

## 六、上线配置

微信公众平台 → 我的小程序 → 订阅消息 → 申请模板 → 选「学习打卡提醒」类目 → 得到 template_id：

```env
WECHAT_SUBSCRIBE_PROVIDER=wechat
WECHAT_SUBSCRIBE_TEMPLATE_CHECKIN=AT0000xxxxx  # 真实 template_id
WECHAT_APPID=wx...
WECHAT_APPSECRET=...
```

---

## 七、文件修改清单

| 文件 | 变更 |
|------|------|
| `backend/app/services/wechat_subscribe_service.py` | 实现 `_get_access_token` + `_send_real_subscribe_message` |
| `tests/unit/test_wechat_subscribe_service.py` | 5 个单元测试（mock httpx） |
| `frontend/miniprogram/src/pages/vocabulary/index.vue` | 完成页加 `requestSubscribeMessage` 授权 |
| `docs/上线前清单.md` | #8 标注已实现 |
