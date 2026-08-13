"""
用户 API 端点

提供以下接口（均需登录态）：
- GET  /users/me                   当前用户信息
- PUT  /users/me                   更新个人信息
- GET  /users/me/addresses          地址列表
- POST /users/me/addresses          新增地址
- PUT  /users/me/addresses/{id}     修改地址
- DELETE /users/me/addresses/{id}   删除地址
- PUT  /users/me/addresses/{id}/default  设为默认地址
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User, UserAddress
from app.schemas.user import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    UserResponse,
    UserUpdateRequest,
)
from app.utils.response import error_response, success_response

router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_current_user_orm(
    current_user_payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """
    从 JWT payload 中提取用户 ID，查询并返回 User ORM 对象。
    因为 get_current_user 返回的是 payload dict，需要转换为 ORM 实例。
    """
    user_id = int(current_user_payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")
    return user


# ──────────────────────────── 个人信息 ────────────────────────────


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
def get_me(current_user: User = Depends(_get_current_user_orm)):
    """返回当前登录用户的个人信息。"""
    return current_user


@router.put("/me", response_model=UserResponse, summary="更新个人信息")
def update_me(
    req: UserUpdateRequest,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """更新当前用户的昵称、头像、性别等可编辑字段。"""
    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个要更新的字段")

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


# ──────────────────────────── 收货地址 CRUD ────────────────────────────


@router.get("/me/addresses", summary="获取地址列表")
def list_addresses(
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """返回当前用户的所有收货地址，默认地址排前，再按创建时间倒序。"""
    addresses = (
        db.query(UserAddress)
        .filter(UserAddress.user_id == current_user.id)
        .order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc())
        .all()
    )
    return success_response(data=[
        AddressResponse.model_validate(a).model_dump() for a in addresses
    ])


@router.post(
    "/me/addresses",
    status_code=status.HTTP_201_CREATED,
    summary="新增收货地址",
)
def create_address(
    req: AddressCreate,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """
    新增一条收货地址。

    - 如果标记为默认地址，会先取消其他默认地址
    - 如果是用户的第一条地址，自动设为默认
    """
    # 如果是第一条地址，自动设为默认
    existing_count = (
        db.query(UserAddress)
        .filter(UserAddress.user_id == current_user.id)
        .count()
    )
    is_default = req.is_default or existing_count == 0

    # 如果设为默认地址，先将其他地址取消默认
    if is_default:
        db.query(UserAddress).filter(
            UserAddress.user_id == current_user.id,
            UserAddress.is_default == True,
        ).update({"is_default": False})

    address = UserAddress(
        user_id=current_user.id,
        contact_name=req.contact_name,
        contact_phone=req.contact_phone,
        province=req.province,
        city=req.city,
        district=req.district,
        detail=req.detail,
        latitude=req.latitude,
        longitude=req.longitude,
        is_default=is_default,
        tag=req.tag,
    )
    db.add(address)
    db.commit()
    db.refresh(address)
    return success_response(data=AddressResponse.model_validate(address).model_dump(), message="地址添加成功")


@router.put("/me/addresses/{address_id}", summary="修改收货地址")
def update_address(
    address_id: int,
    req: AddressUpdate,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """修改指定收货地址（仅限本人地址）。"""
    address = (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址不存在")

    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个要更新的字段")

    # 如果设为默认地址，先将其他地址取消默认
    if update_data.get("is_default"):
        db.query(UserAddress).filter(
            UserAddress.user_id == current_user.id,
            UserAddress.is_default == True,
            UserAddress.id != address_id,
        ).update({"is_default": False})

    for field, value in update_data.items():
        setattr(address, field, value)

    db.commit()
    db.refresh(address)
    return success_response(data=AddressResponse.model_validate(address).model_dump(), message="地址修改成功")


@router.delete("/me/addresses/{address_id}", summary="删除收货地址")
def delete_address(
    address_id: int,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """删除指定收货地址（仅限本人地址）。"""
    address = (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址不存在")

    db.delete(address)
    db.commit()
    return success_response(message="地址已删除")


@router.put(
    "/me/addresses/{address_id}/default",
    summary="设为默认地址",
)
def set_default_address(
    address_id: int,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """将指定收货地址设为默认地址。"""
    address = (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址不存在")

    # 取消其他默认地址
    db.query(UserAddress).filter(
        UserAddress.user_id == current_user.id,
        UserAddress.is_default == True,
        UserAddress.id != address_id,
    ).update({"is_default": False})

    address.is_default = True
    db.commit()
    db.refresh(address)
    return success_response(data=AddressResponse.model_validate(address).model_dump(), message="已设为默认地址")


# ──────────────────────────── 账户余额 ────────────────────────────

from pydantic import BaseModel, Field

class RechargeRequest(BaseModel):
    amount: float = Field(..., ge=-10000, le=10000, description="充值金额（元），正数为充值，负数为扣款")


@router.get("/me/balance", summary="查询余额")
def get_balance(
    current_user: User = Depends(_get_current_user_orm),
):
    """查询当前用户账户余额"""
    return success_response(data={"balance": current_user.balance})


@router.post("/me/recharge", summary="充值余额")
def recharge_balance(
    req: RechargeRequest,
    current_user: User = Depends(_get_current_user_orm),
    db: Session = Depends(get_db),
):
    """充值余额（简易版：直接增加余额，无需支付）"""
    current_user.balance += req.amount
    db.commit()
    db.refresh(current_user)
    return success_response(
        data={"balance": current_user.balance},
        message=f"充值成功 +¥{req.amount:.2f}"
    )
