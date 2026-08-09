"""
认证相关 Schema —— 请求/响应模型
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SendSMSRequest(BaseModel):
    """发送短信验证码请求"""

    phone: str = Field(
        ...,
        pattern=r"^1[3-9]\d{9}$",
        description="手机号（中国大陆11位）",
    )


class PhoneLoginRequest(BaseModel):
    """手机号 + 验证码登录请求"""

    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    sms_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")


class PasswordLoginRequest(BaseModel):
    """手机号 + 密码登录请求"""

    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class RegisterRequest(BaseModel):
    """用户注册请求"""

    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    sms_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")
    nickname: Optional[str] = Field(None, max_length=32, description="用户昵称（可选）")
    password: Optional[str] = Field(None, min_length=6, max_length=128, description="登录密码（可选，不填则仅验证码登录）")


class TokenResponse(BaseModel):
    """登录 / 刷新成功后返回的令牌"""

    access_token: str = Field(..., description="访问令牌（JWT）")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""

    refresh_token: str = Field(..., description="刷新令牌")
