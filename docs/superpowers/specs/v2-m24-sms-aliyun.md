# V2 M24 — 阿里云短信实现

## 背景
`backend/app/services/sms_service.py` 的 `_send_real_sms` = `raise NotImplementedError`。
这导致生产环境以下场景完全无法使用：
- 14 岁以下用户监护人验证（`guardian-verify`）
- 账号注销短信确认（`cancel-account/request`）
- 邀请短信（`send_invite_sms`）

`docs/上线前清单.md` 明确标注为 ⚠️ 硬阻塞。

## 目标
实现阿里云短信 SDK 接入，支持：
1. 验证码短信（`purpose=guardian_verify / cancel_account`）
2. 邀请短信（`purpose=invite_teacher / invite_relative`）

## 技术选型
- SDK：`alibabacloud-dysmsapi20170525`（阿里云官方 Python SDK）
- 配置项（env）：`SMS_ACCESS_KEY_ID`, `SMS_ACCESS_KEY_SECRET`, `SMS_SIGN_NAME`, `SMS_TEMPLATE_CODE_VERIFY`, `SMS_TEMPLATE_CODE_INVITE`
- dev 模式（`sms_provider=placeholder-*`）：保持现有 mock 不变

## 验收标准
- `sms_provider=aliyun` 时调用真实阿里云 API
- 请求失败抛 `AppError(code=503, message="短信发送失败，请稍后重试")`
- 单元测试 mock 阿里云 SDK，验证调用参数正确
- `sms_provider=placeholder-*` 时仍走 mock（向后兼容）
