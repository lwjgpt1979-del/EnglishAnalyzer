"""生产环境启动安全检查（D-077 / 上线准备）。

在 `settings.debug=False` 时（生产模式），检查关键配置项是否仍是 dev placeholder。
若有任何一项命中 placeholder → 启动失败并打印所有问题，避免占位值被部署上线。

DEBUG=True 时全部跳过（不影响本地/CI 测试）。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from app.core.config import Settings


@dataclass
class SafetyIssue:
    key: str
    current_hint: str
    fix: str


def _list_issues(s: Settings) -> list[SafetyIssue]:
    issues: list[SafetyIssue] = []

    # JWT 密钥
    if s.jwt_secret_key == "dev-secret-change-in-production" or len(s.jwt_secret_key) < 32:
        issues.append(SafetyIssue(
            key="JWT_SECRET_KEY",
            current_hint="默认或过短",
            fix="生成 `openssl rand -hex 64` 后填入 .env",
        ))

    # 微信小程序
    if s.wechat_appid.startswith("wx_dev") or "placeholder" in s.wechat_appid.lower():
        issues.append(SafetyIssue(
            key="WECHAT_APPID",
            current_hint=s.wechat_appid,
            fix="在 mp.weixin.qq.com→开发→开发设置 拿真实 AppID",
        ))
    if "placeholder" in s.wechat_appsecret.lower() or s.wechat_appsecret.startswith("dev_"):
        issues.append(SafetyIssue(
            key="WECHAT_APPSECRET",
            current_hint="占位值",
            fix="同上 AppSecret",
        ))

    # DeepSeek
    if s.deepseek_api_key.startswith("sk-placeholder"):
        issues.append(SafetyIssue(
            key="DEEPSEEK_API_KEY",
            current_hint=s.deepseek_api_key,
            fix="https://platform.deepseek.com 申请",
        ))

    # 阿里云 OCR
    if "placeholder" in s.aliyun_ocr_access_key_id.lower():
        issues.append(SafetyIssue(
            key="ALIYUN_OCR_ACCESS_KEY_ID",
            current_hint=s.aliyun_ocr_access_key_id,
            fix="https://ram.console.aliyun.com 创建 RAM 子账号",
        ))

    # 腾讯云 OCR
    if "placeholder" in s.tencent_ocr_secret_id.lower():
        issues.append(SafetyIssue(
            key="TENCENT_OCR_SECRET_ID",
            current_hint=s.tencent_ocr_secret_id,
            fix="https://console.cloud.tencent.com/cam → API 密钥",
        ))

    # 腾讯云 COS
    if "placeholder" in s.cos_secret_id.lower():
        issues.append(SafetyIssue(
            key="COS_SECRET_ID",
            current_hint=s.cos_secret_id,
            fix="同腾讯云 CAM；COS 控制台建桶",
        ))

    # 微信支付
    if "placeholder" in s.wechat_pay_mch_id.lower():
        issues.append(SafetyIssue(
            key="WECHAT_PAY_MCH_ID",
            current_hint=s.wechat_pay_mch_id,
            fix="pay.weixin.qq.com 商户号申请后填入",
        ))
    if "placeholder" in s.wechat_pay_api_key_v3.lower():
        issues.append(SafetyIssue(
            key="WECHAT_PAY_API_KEY_V3",
            current_hint="占位值",
            fix="商户后台设置 API V3 密钥（32 字符随机）",
        ))
    if s.wechat_pay_skip_sig_verify:
        issues.append(SafetyIssue(
            key="WECHAT_PAY_SKIP_SIG_VERIFY",
            current_hint="True",
            fix="必须设为 false，强制开启微信支付签名校验",
        ))

    # SMS（注册<14 监护人验证 + 注销 SMS 必需）
    if s.sms_provider.startswith("placeholder"):
        issues.append(SafetyIssue(
            key="SMS_PROVIDER",
            current_hint=s.sms_provider,
            fix="（1）填阿里云/腾讯云 provider 名 "
                "（2）实现 sms_service._send_real_sms（当前 NotImplementedError）",
        ))

    # 老师认证（生产应由 admin 审核，不能自动通过）
    if s.auto_approve_teacher_cert:
        issues.append(SafetyIssue(
            key="AUTO_APPROVE_TEACHER_CERT",
            current_hint="True",
            fix="设为 false，由平台管理员调 POST /admin/teachers/{id}/review 审核",
        ))

    # 字段级加密主密钥（加密支付渠道密钥；留空则回退派生自 JWT，生产严禁）
    if not s.field_encryption_key or len(s.field_encryption_key) < 32:
        issues.append(SafetyIssue(
            key="FIELD_ENCRYPTION_KEY",
            current_hint="(空) 将回退派生自 JWT" if not s.field_encryption_key else "过短",
            fix="设为 `openssl rand -base64 32`，一次性永久不变（丢失则已存密文无法解密）",
        ))

    # CORS 通配（生产应收紧到 admin/机构前端域名，避免凭证被任意站点携带）
    if s.cors_allow_origins.strip() in ("", "*"):
        issues.append(SafetyIssue(
            key="CORS_ALLOW_ORIGINS",
            current_hint=s.cors_allow_origins or "(空)",
            fix="填实际前端域名（逗号分隔），如 https://admin.goodgrammar.top,https://inst.goodgrammar.top",
        ))

    return issues


def run_production_safety_check(settings: Settings) -> None:
    """启动期调用：debug=False 时检查关键配置；命中 placeholder 则 fail-fast。"""
    if settings.debug:
        return  # 本地/CI 跳过

    issues = _list_issues(settings)
    if not issues:
        print("[safety] ✅ 生产配置检查通过", flush=True)
        return

    print("\n" + "=" * 78, flush=True)
    print("❌ 生产环境启动安全检查失败 —— 以下配置仍是 dev placeholder：", flush=True)
    print("=" * 78, flush=True)
    for i, iss in enumerate(issues, 1):
        print(f"\n[{i}] {iss.key}", flush=True)
        print(f"    当前：{iss.current_hint}", flush=True)
        print(f"    修复：{iss.fix}", flush=True)
    print("\n" + "=" * 78, flush=True)
    print(
        f"共 {len(issues)} 项需要修复。详见 docs/上线前清单.md C/D 节。\n"
        "如临时绕过（仅 staging 等），可在 .env 设 DEBUG=true。",
        flush=True,
    )
    print("=" * 78 + "\n", flush=True)
    sys.exit(1)
