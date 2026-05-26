from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库
    database_url: str
    async_database_url: str

    # 微信小程序
    wechat_appid: str = "wx_dev_placeholder"
    wechat_appsecret: str = "dev_secret_placeholder"
    wechat_code2session_url: str = (
        "https://api.weixin.qq.com/sns/jscode2session"
    )

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120   # 2 小时
    refresh_token_expire_days: int = 30

    # AI 分析（Anthropic Claude）
    anthropic_api_key: str = "sk-ant-placeholder-for-dev"

    # 微信支付 v3
    wechat_pay_mch_id: str = "placeholder_mch_id"
    wechat_pay_api_key_v3: str = "placeholder32charsapikey12345678"  # 32 chars
    wechat_pay_cert_serial: str = "placeholder_cert_serial"
    wechat_pay_private_key_pem: str = "placeholder_private_key_pem"
    wechat_pay_notify_url: str = "https://api.example.com/api/v1/webhooks/wx-pay"
    # dev 模式跳过微信签名验证（生产环境必须设为 false）
    wechat_pay_skip_sig_verify: bool = True

    # 腾讯云 COS 图片存储
    cos_secret_id: str = "placeholder_secret_id"
    cos_secret_key: str = "placeholder_secret_key"
    cos_bucket: str = "enggramer-dev-1234567890"
    cos_region: str = "ap-guangzhou"
    cos_base_url: str = "https://enggramer-dev-1234567890.cos.ap-guangzhou.myqcloud.com"

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
