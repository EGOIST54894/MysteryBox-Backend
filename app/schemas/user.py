"""
用户相关 Schema —— 个人信息、收货地址
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────── 用户信息 ────────────────────────────


class UserResponse(BaseModel):
    """用户信息响应"""

    id: int
    phone: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[int] = Field(None, description="性别: 0=未知, 1=男, 2=女")
    status: int = Field(..., description="账户状态: 1=正常, 0=禁用")
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """更新个人信息请求（所有字段可选）"""

    nickname: Optional[str] = Field(None, max_length=32, description="用户昵称")
    avatar_url: Optional[str] = Field(None, max_length=512, description="头像URL")
    gender: Optional[int] = Field(None, ge=0, le=2, description="性别: 0=未知, 1=男, 2=女")


# ──────────────────────────── 收货地址 ────────────────────────────


class AddressCreate(BaseModel):
    """新增收货地址请求"""

    contact_name: str = Field(..., max_length=32, description="收货人姓名")
    contact_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="收货人手机号")
    province: str = Field(..., max_length=32, description="省份")
    city: str = Field(..., max_length=32, description="城市")
    district: str = Field(..., max_length=32, description="区/县")
    detail: str = Field(..., max_length=255, description="详细地址（门牌号等）")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    is_default: bool = Field(default=False, description="是否设为默认地址")


class AddressUpdate(BaseModel):
    """修改收货地址请求（所有字段可选）"""

    contact_name: Optional[str] = Field(None, max_length=32, description="收货人姓名")
    contact_phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$", description="收货人手机号")
    province: Optional[str] = Field(None, max_length=32, description="省份")
    city: Optional[str] = Field(None, max_length=32, description="城市")
    district: Optional[str] = Field(None, max_length=32, description="区/县")
    detail: Optional[str] = Field(None, max_length=255, description="详细地址")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    is_default: Optional[bool] = Field(None, description="是否设为默认地址")


class AddressResponse(BaseModel):
    """收货地址响应"""

    id: int
    user_id: int
    contact_name: str
    contact_phone: str
    province: str
    city: str
    district: str
    detail: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}
