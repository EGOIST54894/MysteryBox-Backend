"""
订单相关 Schema —— 创建、查询、状态变更
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────── 订单创建 ────────────────────────────


class OrderCreate(BaseModel):
    """下单请求"""

    box_id: int = Field(..., gt=0, description="盲盒ID")
    address_id: Optional[int] = Field(default=None, gt=0, description="收货地址ID（可选）")
    quantity: int = Field(default=1, ge=1, le=99, description="购买数量")
    group_id: Optional[int] = Field(None, description="拼团ID（参团时传入）")


# ──────────────────────────── 订单状态变更 ────────────────────────────


class OrderStatusUpdate(BaseModel):
    """订单状态变更请求"""

    order_status: str = Field(
        ...,
        description="目标状态: pending_pay=待支付, paid=已支付, preparing=制作中, "
        "ready=待取货, delivering=配送中, completed=已完成, cancelled=已取消, refunding=退款中, refunded=已退款",
    )
    cancel_reason: Optional[str] = Field(None, max_length=512, description="取消原因（取消时可选填写）")


# ──────────────────────────── 订单内嵌子模型 ────────────────────────────


class OrderBoxBrief(BaseModel):
    """订单中的盲盒摘要信息"""

    id: int
    title: str
    cover_image: Optional[str] = None
    box_type: str

    model_config = {"from_attributes": True}


class OrderAddressBrief(BaseModel):
    """订单中的收货地址摘要"""

    id: int
    contact_name: str
    contact_phone: str
    province: str
    city: str
    district: str
    detail: str

    model_config = {"from_attributes": True}


# ──────────────────────────── 订单响应 ────────────────────────────


class OrderResponse(BaseModel):
    """订单完整信息响应"""

    id: int
    order_no: str
    user_id: int
    box_id: int
    address_id: int
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    discount_amount: Decimal = Field(default=Decimal("0.00"))
    paid_amount: Decimal
    group_id: Optional[int] = None
    group_role: Optional[str] = Field(None, description="拼团角色: leader=团长, member=团员")
    order_status: str
    cancel_reason: Optional[str] = None
    box: Optional[OrderBoxBrief] = Field(None, description="关联盲盒摘要")
    address: Optional[OrderAddressBrief] = Field(None, description="收货地址摘要")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
