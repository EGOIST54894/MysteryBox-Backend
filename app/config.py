"""
应用配置模块
使用 pydantic-settings 管理所有配置项，支持从环境变量或 .env 文件加载。
"""

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ==================== 应用基础信息 ====================
    APP_NAME: str = "外卖盲盒"
    DEBUG: bool = True
    VERSION: str = "1.0.0"

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = "sqlite:///./mystery_box.db"

    # ==================== JWT 认证配置 ====================
    SECRET_KEY: str = "change-me-to-a-secure-random-string-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ==================== 短信验证码配置 ====================
    SMS_CODE_LENGTH: int = 6
    SMS_CODE_EXPIRE_MINUTES: int = 5

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"

    # ==================== 支付配置 ====================
    # mock: 模拟支付 | sandbox: 沙箱环境 | production: 生产环境
    PAYMENT_MODE: str = "mock"

    # ==================== CORS 跨域配置 ====================
    CORS_ORIGINS: List[str] = ["*"]

    @property
    def upload_dir_path(self) -> Path:
        """返回上传目录的 Path 对象，确保为绝对路径"""
        return Path(self.UPLOAD_DIR).resolve()


# 全局单例配置对象
settings = Settings()
