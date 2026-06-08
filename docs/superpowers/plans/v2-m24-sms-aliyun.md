# V2 M24 Plan — 阿里云短信接入

## 步骤

### 1. 依赖
```
alibabacloud-dysmsapi20170525>=2.0.0
alibabacloud-tea-openapi>=0.3.0
```
添加到 `backend/requirements.txt`（或 pyproject.toml）

### 2. Config
`app/core/config.py` 新增：
```python
sms_access_key_id: str = ""
sms_access_key_secret: str = ""
sms_sign_name: str = "engGramer"
sms_template_code_verify: str = ""
sms_template_code_invite: str = ""
```

### 3. `sms_service._send_real_sms` 实现
```python
async def _send_real_sms(*, phone: str, code: str, purpose: str) -> None:
    from alibabacloud_dysmsapi20170525.client import Client
    from alibabacloud_dysmsapi20170525.models import SendSmsRequest
    from alibabacloud_tea_openapi.models import Config
    cfg = Config(
        access_key_id=settings.sms_access_key_id,
        access_key_secret=settings.sms_access_key_secret,
        endpoint="dysmsapi.aliyuncs.com",
    )
    client = Client(cfg)
    template_code = (
        settings.sms_template_code_verify
        if purpose in ("guardian_verify", "cancel_account")
        else settings.sms_template_code_invite
    )
    req = SendSmsRequest(
        phone_numbers=phone,
        sign_name=settings.sms_sign_name,
        template_code=template_code,
        template_param=f'{{"code":"{code}"}}',
    )
    resp = await asyncio.to_thread(client.send_sms, req)
    if resp.body.code != "OK":
        raise AppError(code=503, message=f"短信发送失败：{resp.body.message}")
```

### 4. TDD
新建 `tests/unit/test_sms_service.py`
- mock 阿里云 SDK Client
- `test_send_sms_code_dev_mode_does_not_call_sdk`
- `test_send_sms_code_prod_mode_calls_sdk`
- `test_send_sms_code_sdk_error_raises_app_error`

### 5. 文档更新
`docs/上线前清单.md` D-4 标注为已实现（待填 env 真实 key）

## 文件修改清单
- `backend/requirements.txt`（新增 SDK 依赖）
- `backend/app/core/config.py`（新增 4 个 sms 配置项）
- `backend/app/services/sms_service.py`（实现 `_send_real_sms`）
- `tests/unit/test_sms_service.py`（新建）
- `deploy/.env.production.example`（补充 SMS_* 示例值）
