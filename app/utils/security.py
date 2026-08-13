"""
安全工具模块
提供密码哈希、JWT Token 生成与解析、短信验证码生成等功能。
"""

import hashlib
import os
import random
from datetime import datetime, timedelta, timezone

from jose import jwt
from jose import JWTError

from app.config import settings


# ==================== 密码哈希工具 ====================
def hash_password(password: str) -> str:
    """
    使用 SHA256 + 随机盐 对密码进行哈希处理。

    Args:
        password: 明文密码

    Returns:
        salt$hash 格式的密码字符串
    """
    salt = os.urandom(32).hex()
    key = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
    return f"{salt}${key}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与哈希密码匹配。

    Args:
        plain_password: 明文密码
        hashed_password: salt$hash 格式的哈希密码

    Returns:
        True 匹配成功，False 匹配失败
    """
    try:
        salt, stored_hash = hashed_password.split("$")
        key = hashlib.sha256(f"{salt}{plain_password}".encode("utf-8")).hexdigest()
        return key == stored_hash
    except (ValueError, AttributeError):
        return False


# ==================== JWT Token 工具 ====================
def _create_token(data: dict, expires_delta: timedelta) -> str:
    """
    创建 JWT Token 的内部通用方法。

    Args:
        data: 要编码到 token 中的数据（需包含 "sub" 字段）
        expires_delta: 过期时间增量

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    """
    创建访问令牌 (Access Token)。
    有效期由 ACCESS_TOKEN_EXPIRE_MINUTES 配置决定。

    Args:
        data: 包含用户信息的字典，至少包含 "sub"（用户ID）和 "role"（角色）

    Returns:
        JWT 访问令牌字符串

    Example:
        >>> token = create_access_token({"sub": "42", "role": "user"})
    """
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = data.copy()
    token_data["type"] = "access"
    return _create_token(token_data, expires_delta)


def create_refresh_token(data: dict) -> str:
    """
    创建刷新令牌 (Refresh Token)。
    有效期由 REFRESH_TOKEN_EXPIRE_DAYS 配置决定。

    Args:
        data: 包含用户信息的字典，至少包含 "sub"（用户ID）

    Returns:
        JWT 刷新令牌字符串
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token_data = data.copy()
    token_data["type"] = "refresh"
    return _create_token(token_data, expires_delta)


def decode_token(token: str) -> dict:
    """
    解码并验证 JWT Token。

    Args:
        token: JWT token 字符串

    Returns:
        解码后的 payload 字典，包含 sub, role, iat, exp 等字段

    Raises:
        JWTError: token 无效、过期或签名不匹配
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ==================== 短信验证码工具 ====================
def generate_sms_code() -> str:
    """
    生成 6 位数字短信验证码。

    Returns:
        6 位数字字符串，例如 "384729"
    """
    return "".join(random.choices("0123456789", k=settings.SMS_CODE_LENGTH))
