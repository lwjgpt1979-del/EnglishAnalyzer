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

    # AI 大模型（默认 DeepSeek，OpenAI 兼容协议）
    # 换厂商只需改 llm_base_url + llm_model + 对应 api_key，业务 service 零改动。
    deepseek_api_key: str = "sk-placeholder-for-dev"  # LLM api key（dev 以 sk-placeholder 开头触发 mock）
    llm_base_url: str = "https://api.deepseek.com"     # OpenAI 兼容 endpoint
    llm_model: str = "deepseek-chat"                   # 模型名

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

    # 词力通图背单词媒体（dev 以 placeholder 触发 mock；真生成留接缝，需预算 + key）
    image_provider: str = "mock"
    image_api_key: str = "img-placeholder-for-dev"
    image_count_per_word: int = 3
    tts_provider: str = "mock"
    tts_api_key: str = "tts-placeholder-for-dev"

    # 阿里云 OCR（印刷体识别）
    # 在 https://ram.console.aliyun.com 创建 RAM 子账号并授予 OCR 权限
    aliyun_ocr_access_key_id: str = "placeholder_aliyun_ak_id"
    aliyun_ocr_access_key_secret: str = "placeholder_aliyun_ak_secret"

    # 腾讯云 OCR（手写体识别）
    # 使用与 COS 相同的子账号即可（需开通 OCR 服务权限）
    tencent_ocr_secret_id: str = "placeholder_tencent_ocr_sid"
    tencent_ocr_secret_key: str = "placeholder_tencent_ocr_skey"

    # SMS 短信服务
    sms_provider: str = "placeholder-dev"  # 'placeholder-*' 触发 dev mock；生产填真实 provider 名

    # 微信订阅消息（打卡提醒，D-108）
    wechat_subscribe_provider: str = "placeholder-dev"  # 'placeholder-*' 触发 dev mock
    wechat_subscribe_template_checkin: str = "placeholder-template-checkin"

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # 老师认证
    auto_approve_teacher_cert: bool = True  # dev 自动通过；生产置 False 由 admin 审核


settings = Settings()
