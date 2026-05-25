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

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
