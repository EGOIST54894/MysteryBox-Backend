"""
认证业务逻辑模块

包含：
- 短信验证码的发送与校验（内存模拟，生产环境请替换为 Redis）
- 用户注册
- 手机号 + 验证码登录
- 手机号 + 密码登录
- Token 刷新
"""

import time
from datetime import datetime, timezone
from typing import Optional

from jose import JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.auth import TokenResponse
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

# ──────────────────────────── 模拟短信验证码存储 ────────────────────────────
# 生产环境应替换为 Redis：键 = f"sms:{phone}"，值 = code，设置 TTL
sms_codes: dict[str, dict] = {}


def _clean_expired_codes() -> None:
    """清理过期的验证码（简单定时清理，避免内存泄漏）"""
    now = time.time()
    expired_phones = [
        phone for phone, data in sms_codes.items() if data["expires_at"] < now
    ]
    for phone in expired_phones:
        del sms_codes[phone]


# ──────────────────────────── 发送验证码 ────────────────────────────


def send_sms_code(phone: str) -> str:
    """
    生成并"发送"验证码（当前仅打印到控制台，生产环境对接短信服务商）。

    Returns:
        生成的验证码（调试用，生产环境不应返回）
    """
    _clean_expired_codes()

    # 检查是否在60秒内重复发送
    existing = sms_codes.get(phone)
    if existing and (time.time() - existing.get("sent_at", 0)) < 60:
        raise ValueError("验证码已发送，请60秒后再试")

    from app.utils.security import generate_sms_code

    code = generate_sms_code()

    sms_codes[phone] = {
        "code": code,
        "expires_at": time.time() + settings.SMS_CODE_EXPIRE_MINUTES * 60,
        "sent_at": time.time(),
    }

    # TODO: 生产环境在此对接短信服务商 API
    print(f"[模拟短信] 手机号 {phone} 的验证码为: {code}")

    return code


# ──────────────────────────── 校验验证码 ────────────────────────────


def verify_sms_code(phone: str, code: str) -> bool:
    """校验短信验证码是否正确且在有效期内。"""
    _clean_expired_codes()

    data = sms_codes.get(phone)
    if not data:
        return False

    if time.time() > data["expires_at"]:
        del sms_codes[phone]
        return False

    if data["code"] != code:
        return False

    # 验证成功即删除，保证一次性使用
    del sms_codes[phone]
    return True


# ──────────────────────────── 用户注册 ────────────────────────────


def register_user(
    phone: str,
    code: str,
    nickname: Optional[str] = None,
    password: Optional[str] = None,
    db: Session = None,
) -> "User":
    """
    注册新用户。

    流程：
    1. 校验验证码
    2. 检查手机号是否已注册
    3. 创建 User 记录（有密码则 hash 存储，无密码则存空串）
    """
    from app.models.user import User

    if not verify_sms_code(phone, code):
        raise ValueError("验证码错误或已过期")

    # 检查手机号是否已注册
    existing = db.query(User).filter(User.phone == phone).first()
    if existing:
        raise ValueError("该手机号已注册")

    # password_hash 字段 non-nullable，未设密码时存储空字符串
    pwd_hash = hash_password(password) if password else ""

    user = User(
        phone=phone,
        nickname=nickname or f"用户{phone[-4:]}",
        password_hash=pwd_hash,
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ──────────────────────────── 手机号 + 验证码登录 ────────────────────────────


def login_by_phone_code(phone: str, code: str, db: Session) -> TokenResponse:
    """
    手机号 + 验证码登录。

    流程：
    1. 校验验证码
    2. 查找用户（未注册则自动注册）
    3. 签发 JWT 令牌
    """
    from app.models.user import User

    if not verify_sms_code(phone, code):
        raise ValueError("验证码错误或已过期")

    user = db.query(User).filter(User.phone == phone).first()

    # 如果用户不存在，自动注册（无密码用户）
    if not user:
        user = User(
            phone=phone,
            nickname=f"用户{phone[-4:]}",
            password_hash="",
            status=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 检查账户状态
    if user.status != 1:
        raise ValueError("账户已被禁用，请联系客服")

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return generate_tokens(user.id)


# ──────────────────────────── 手机号 + 密码登录 ────────────────────────────


def login_by_password(phone: str, password: str, db: Session) -> TokenResponse:
    """
    手机号 + 密码登录。

    流程：
    1. 查找用户
    2. 校验密码
    3. 签发 JWT 令牌
    """
    from app.models.user import User

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise ValueError("手机号未注册")

    if user.status != 1:
        raise ValueError("账户已被禁用，请联系客服")

    if not user.password_hash:
        raise ValueError("该账号未设置密码，请使用验证码登录")

    if not verify_password(password, user.password_hash):
        raise ValueError("密码错误")

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return generate_tokens(user.id)


# ──────────────────────────── Token 刷新 ────────────────────────────


def refresh_access_token(refresh_token: str) -> TokenResponse:
    """
    使用 refresh_token 换取新的 access_token（滚动刷新策略）。

    Raises:
        ValueError: token 无效、过期或类型不匹配
    """
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise ValueError("无效的刷新令牌")

    if payload.get("type") != "refresh":
        raise ValueError("令牌类型错误，请使用 refresh_token")

    user_id = payload.get("sub")
    if user_id is None:
        raise ValueError("无效的令牌载荷")

    return generate_tokens(int(user_id))


# ──────────────────────────── Token 生成 ────────────────────────────


def generate_tokens(user_id: int) -> TokenResponse:
    """为指定用户（user角色）生成 access_token 和 refresh_token。"""
    access_token = create_access_token(
        data={"sub": str(user_id), "type": "access", "role": "user"}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user_id), "type": "refresh", "role": "user"}
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


def generate_tokens_for_role(entity_id: int, role: str) -> TokenResponse:
    """为指定角色（user/merchant/delivery）生成 access_token 和 refresh_token。"""
    access_token = create_access_token(
        data={"sub": str(entity_id), "type": "access", "role": role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(entity_id), "type": "refresh", "role": role}
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


# ──────────────────────────── 商家注册 ────────────────────────────


def register_merchant(
    phone: str,
    password: str,
    store_name: str,
    nickname: str | None = None,
    db: Session = None,
) -> "Merchant":
    """注册新商家，返回 Token"""
    from app.models.merchant import Merchant

    existing = db.query(Merchant).filter(Merchant.phone == phone).first()
    if existing:
        raise ValueError("该手机号已注册")

    merchant = Merchant(
        phone=phone,
        password_hash=hash_password(password),
        store_name=store_name,
        nickname=nickname or store_name,
        status=1,  # 已审核通过（演示环境简化）
        province="广东省",
        city="深圳市",
        district="南山区",
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


# ──────────────────────────── 配送员注册 ────────────────────────────


def register_delivery(
    phone: str,
    password: str,
    real_name: str,
    nickname: str | None = None,
    db: Session = None,
) -> "DeliveryPersonnel":
    """注册新配送员，返回 Token"""
    from app.models.delivery import DeliveryPersonnel

    existing = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.phone == phone).first()
    if existing:
        raise ValueError("该手机号已注册")

    dp = DeliveryPersonnel(
        phone=phone,
        password_hash=hash_password(password),
        real_name=real_name,
        nickname=nickname or real_name,
        id_card="440301199001010000",  # 演示环境默认
        status=1,  # 在线（演示环境简化）
    )
    db.add(dp)
    db.commit()
    db.refresh(dp)
    return dp
