"""
认证 API 端点

提供以下接口：
- POST /auth/send-sms        发送验证码
- POST /auth/login/phone     手机号 + 验证码登录
- POST /auth/login/password  手机号 + 密码登录
- POST /auth/login/admin     管理员登录（用户名 + 密码）
- POST /auth/login/merchant  商家登录（手机号 + 密码）
- POST /auth/login/delivery  配送员登录（手机号 + 密码）
- POST /auth/register        用户注册
- POST /auth/refresh         刷新 Token
- POST /auth/logout          退出登录
- GET  /auth/userinfo        获取当前登录用户信息
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.auth import (
    PasswordLoginRequest,
    PhoneLoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SendSMSRequest,
    TokenResponse,
)
from app.services.auth_service import (
    generate_tokens,
    generate_tokens_for_role,
    login_by_password,
    login_by_phone_code,
    refresh_access_token,
    register_delivery,
    register_merchant,
    register_user,
    send_sms_code,
)
from app.utils.response import error_response, success_response
from app.utils.security import create_access_token, create_refresh_token, verify_password

router = APIRouter()


# ──────────────────────────── 后台角色登录请求模型 ────────────────────────────

class AdminLoginRequest(BaseModel):
    """管理员登录请求"""
    username: str = Field(..., min_length=2, max_length=50, description="管理员用户名")
    password: str = Field(..., min_length=4, max_length=128, description="密码")


class RoleBasedLoginRequest(BaseModel):
    """商家/配送员手机号密码登录请求"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    password: str = Field(..., min_length=4, max_length=128, description="密码")


@router.post("/send-sms", summary="发送短信验证码")
def send_sms(req: SendSMSRequest):
    """
    向指定手机号发送短信验证码。

    - 同一手机号 60 秒内不可重复发送
    - 验证码有效期由配置项 SMS_CODE_EXPIRE_MINUTES 决定
    """
    try:
        code = send_sms_code(req.phone)
        # 生产环境不应返回 code，此处仅为调试方便
        return success_response(
            message="验证码已发送",
            data={"phone": req.phone, "debug_code": code},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))


@router.post("/login/phone", summary="手机号验证码登录")
def login_by_phone(req: PhoneLoginRequest, db: Session = Depends(get_db)):
    """
    使用手机号和短信验证码登录。

    - 如果手机号未注册，将自动创建账户
    - 返回 access_token、refresh_token 和用户信息
    """
    try:
        token = login_by_phone_code(req.phone, req.sms_code, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 查询用户信息用于响应
    from app.models.user import User
    user = db.query(User).filter(User.phone == req.phone).first()

    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "user": {
            "id": user.id if user else 0,
            "phone": req.phone,
            "nickname": user.nickname if user else "",
            "avatar": user.avatar_url if user else "",
            "role": "user",
            "created_at": user.created_at.isoformat() if (user and user.created_at) else "",
        },
    }


@router.post("/login/password", summary="手机号密码登录")
def login_by_pwd(req: PasswordLoginRequest, db: Session = Depends(get_db)):
    """
    使用手机号和密码登录。

    - 需要已注册且设置了密码的账户
    - 返回 access_token、refresh_token 和用户信息
    """
    try:
        token = login_by_password(req.phone, req.password, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 查询用户信息用于响应
    from app.models.user import User
    user = db.query(User).filter(User.phone == req.phone).first()

    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "user": {
            "id": user.id if user else 0,
            "phone": req.phone,
            "nickname": user.nickname if user else "",
            "avatar": user.avatar_url if user else "",
            "role": "user",
            "created_at": user.created_at.isoformat() if (user and user.created_at) else "",
        },
    }


@router.post("/register", summary="用户注册（短信验证码）")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    注册新用户（需短信验证码）。

    - 需要先通过 /send-sms 获取验证码
    - 可选填写昵称和密码
    - 注册成功后直接返回 Token 和用户信息（自动登录）
    """
    try:
        from app.models.user import User
        user = register_user(
            phone=req.phone,
            code=req.sms_code,
            nickname=req.nickname,
            password=req.password,
            db=db,
        )
        # 注册成功即登录，生成 Token
        token = generate_tokens(user.id)
        return {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "user_id": user.id,
            "user": {
                "id": user.id,
                "phone": user.phone,
                "nickname": user.nickname or "",
                "avatar": user.avatar_url or "",
                "role": "user",
                "created_at": user.created_at.isoformat() if user.created_at else "",
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 用户密码注册 ────────────────────────────


class UserPasswordRegisterRequest(BaseModel):
    """用户密码注册请求（无需短信验证码）"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    password: str = Field(..., min_length=4, max_length=128, description="密码")
    nickname: str | None = Field(None, max_length=50, description="用户昵称")


@router.post("/register/password", summary="用户密码注册")
def register_user_password(req: UserPasswordRegisterRequest, db: Session = Depends(get_db)):
    """
    使用手机号+密码注册新用户（无需短信验证码）。

    - 手机号 + 密码 + 可选昵称
    - 注册成功后直接返回 Token 和用户信息（自动登录）
    """
    from app.models.user import User

    existing = db.query(User).filter(User.phone == req.phone).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该手机号已注册")

    from app.utils.security import hash_password
    user = User(
        phone=req.phone,
        nickname=req.nickname or f"用户{req.phone[-4:]}",
        password_hash=hash_password(req.password),
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = generate_tokens(user.id)
    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_type": token.token_type,
        "user_id": user.id,
        "user": {
            "id": user.id,
            "phone": user.phone,
            "nickname": user.nickname or "",
            "avatar": user.avatar_url or "",
            "role": "user",
            "created_at": user.created_at.isoformat() if user.created_at else "",
        },
    }


# ──────────────────────────── 商家注册 ────────────────────────────


class MerchantRegisterRequest(BaseModel):
    """商家注册请求"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    password: str = Field(..., min_length=4, max_length=128, description="密码")
    store_name: str = Field(..., min_length=1, max_length=100, description="店铺名称")
    nickname: str | None = Field(None, max_length=50, description="商家昵称")


@router.post("/register/merchant", summary="商家注册")
def register_merchant_api(req: MerchantRegisterRequest, db: Session = Depends(get_db)):
    """
    注册新商家账号。

    - 手机号 + 密码 + 店铺名 + 可选昵称
    - 注册成功后直接返回 Token 和商家信息（自动登录）
    - 演示环境默认审核通过（status=1）
    """
    try:
        merchant = register_merchant(
            phone=req.phone,
            password=req.password,
            store_name=req.store_name,
            nickname=req.nickname,
            db=db,
        )
        token = generate_tokens_for_role(merchant.id, "merchant")
        return {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "user_id": merchant.id,
            "user": {
                "id": merchant.id,
                "phone": merchant.phone,
                "nickname": merchant.nickname or merchant.store_name,
                "avatar": merchant.avatar_url or "",
                "role": "merchant",
                "created_at": merchant.created_at.isoformat() if merchant.created_at else "",
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 配送员注册 ────────────────────────────


class DeliveryRegisterRequest(BaseModel):
    """配送员注册请求"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    password: str = Field(..., min_length=4, max_length=128, description="密码")
    real_name: str = Field(..., min_length=1, max_length=30, description="真实姓名")
    nickname: str | None = Field(None, max_length=50, description="配送员昵称")


@router.post("/register/delivery", summary="配送员注册")
def register_delivery_api(req: DeliveryRegisterRequest, db: Session = Depends(get_db)):
    """
    注册新配送员账号。

    - 手机号 + 密码 + 真实姓名 + 可选昵称
    - 注册成功后直接返回 Token 和配送员信息（自动登录）
    - 演示环境默认在线状态（status=1）
    """
    try:
        dp = register_delivery(
            phone=req.phone,
            password=req.password,
            real_name=req.real_name,
            nickname=req.nickname,
            db=db,
        )
        token = generate_tokens_for_role(dp.id, "delivery")
        return {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "user_id": dp.id,
            "user": {
                "id": dp.id,
                "phone": dp.phone,
                "nickname": dp.nickname or dp.real_name,
                "avatar": dp.avatar_url or "",
                "role": "delivery",
                "created_at": dp.created_at.isoformat() if dp.created_at else "",
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 管理员登录 ────────────────────────────


@router.post("/login/admin", response_model=TokenResponse, summary="管理员登录")
def login_admin(req: AdminLoginRequest, db: Session = Depends(get_db)):
    """
    管理员用户名 + 密码登录。

    - JWT 中 role 设为 'admin'
    - 校验管理员账户状态（必须 status=1）
    """
    from app.models.admin import Admin

    admin = db.query(Admin).filter(Admin.username == req.username).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或密码错误",
        )

    if admin.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账户已被禁用",
        )

    if not verify_password(req.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或密码错误",
        )

    # 生成含 role=admin 的 JWT
    access_token = create_access_token(
        data={"sub": str(admin.id), "type": "access", "role": "admin"}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(admin.id), "type": "refresh", "role": "admin"}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


# ──────────────────────────── 商家登录 ────────────────────────────


@router.post("/login/merchant", summary="商家登录")
def login_merchant(req: RoleBasedLoginRequest, db: Session = Depends(get_db)):
    """
    商家手机号 + 密码登录。

    - JWT 中 role 设为 'merchant'
    - 校验商家状态（审核通过 status=1 才可登录）
    - 返回 access_token、refresh_token 和商家信息
    """
    from app.models.merchant import Merchant

    merchant = db.query(Merchant).filter(Merchant.phone == req.phone).first()
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号未注册",
        )

    if merchant.status == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="商家正在审核中，请耐心等待",
        )
    if merchant.status == 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="商家审核未通过",
        )
    if merchant.status == 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="商家已被禁用",
        )

    if not verify_password(req.password, merchant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误",
        )

    # 生成含 role=merchant 的 JWT
    access_token = create_access_token(
        data={"sub": str(merchant.id), "type": "access", "role": "merchant"}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(merchant.id), "type": "refresh", "role": "merchant"}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": merchant.id,
            "phone": merchant.phone,
            "nickname": merchant.nickname or merchant.store_name,
            "avatar": merchant.avatar_url or "",
            "role": "merchant",
            "created_at": merchant.created_at.isoformat() if merchant.created_at else "",
        },
    }


# ──────────────────────────── 配送员登录 ────────────────────────────


@router.post("/login/delivery", summary="配送员登录")
def login_delivery(req: RoleBasedLoginRequest, db: Session = Depends(get_db)):
    """
    配送员手机号 + 密码登录。

    - JWT 中 role 设为 'delivery'
    - 校验配送员状态（在线 status=1 才可登录）
    - 返回 access_token、refresh_token 和配送员信息
    """
    from app.models.delivery import DeliveryPersonnel

    dp = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.phone == req.phone).first()
    if not dp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号未注册",
        )

    if dp.status == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="配送员正在审核中，请耐心等待",
        )
    if dp.status == 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="配送员已被禁用",
        )

    if not verify_password(req.password, dp.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误",
        )

    # 生成含 role=delivery 的 JWT
    access_token = create_access_token(
        data={"sub": str(dp.id), "type": "access", "role": "delivery"}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(dp.id), "type": "refresh", "role": "delivery"}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": dp.id,
            "phone": dp.phone,
            "nickname": dp.nickname or dp.real_name,
            "avatar": dp.avatar_url or "",
            "role": "delivery",
            "created_at": dp.created_at.isoformat() if dp.created_at else "",
        },
    }


# ──────────────────────────── Token 刷新 ────────────────────────────


@router.post("/refresh", response_model=TokenResponse, summary="刷新访问令牌")
def refresh_token(req: RefreshTokenRequest):
    """
    使用 refresh_token 换取新的 access_token。

    - 采用滚动刷新策略：每次刷新同时发放新的 refresh_token
    - 旧的 refresh_token 作废
    """
    try:
        return refresh_access_token(req.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout", summary="退出登录")
def logout():
    """
    退出登录。

    当前为简化实现，仅返回成功。
    后续可通过 Token 黑名单（Redis）实现真正的 Token 吊销。
    """
    return success_response(message="已退出登录")


# ──────────────────────────── 获取当前用户信息 ────────────────────────────


@router.get("/userinfo", summary="获取当前登录用户信息")
def get_userinfo(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None, alias="Authorization"),
):
    """
    根据 JWT Token 获取当前登录用户的信息。

    支持三种角色：user / merchant / delivery。
    从 Authorization header 中解析 JWT，根据 role 查询对应表。
    """
    from app.utils.security import decode_token
    from app.models.user import User
    from app.models.merchant import Merchant
    from app.models.delivery import DeliveryPersonnel

    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证信息")

    # 提取 Bearer token
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")

    sub = payload.get("sub")
    role = payload.get("role", "user")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌载荷")

    entity_id = int(sub)

    if role == "merchant":
        entity = db.query(Merchant).filter(Merchant.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商家不存在")
        return success_response(data={
            "id": entity.id,
            "phone": entity.phone,
            "nickname": entity.nickname or entity.store_name,
            "avatar": entity.avatar_url or "",
            "role": "merchant",
            "created_at": entity.created_at.isoformat() if entity.created_at else "",
        })

    elif role == "delivery":
        entity = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配送员不存在")
        return success_response(data={
            "id": entity.id,
            "phone": entity.phone,
            "nickname": entity.nickname or entity.real_name,
            "avatar": entity.avatar_url or "",
            "role": "delivery",
            "created_at": entity.created_at.isoformat() if entity.created_at else "",
        })

    else:
        entity = db.query(User).filter(User.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return success_response(data={
            "id": entity.id,
            "phone": entity.phone,
            "nickname": entity.nickname or "",
            "avatar": entity.avatar_url or "",
            "role": "user",
            "created_at": entity.created_at.isoformat() if entity.created_at else "",
        })
