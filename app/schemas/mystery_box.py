"""
盲盒相关 Schema —— 创建、编辑、查询、响应
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────── 盲盒创建 & 编辑 ────────────────────────────


class BoxCreate(BaseModel):
    """盲盒创建请求（商家端）"""

    title: str = Field(..., min_length=1, max_length=128, description="盲盒标题")
    description: Optional[str] = Field(None, max_length=1024, description="盲盒描述")
    cover_image: Optional[str] = Field(None, max_length=512, description="封面图片URL")
    box_type: str = Field(..., description="盲盒类型: surplus=余量盲盒, group_buy=拼团盲盒, surprise=惊喜盲盒")
    original_price: Decimal = Field(..., gt=0, description="原价")
    sale_price: Decimal = Field(..., gt=0, description="售价")
    stock: int = Field(..., ge=0, description="库存数量")
    pickup_start_time: Optional[datetime] = Field(None, description="可取餐开始时间")
    pickup_end_time: Optional[datetime] = Field(None, description="可取餐结束时间")
    tags: Optional[list[str]] = Field(default_factory=list, description="标签列表（可选）")


class BoxUpdate(BaseModel):
    """盲盒编辑请求（所有字段可选）"""

    title: Optional[str] = Field(None, min_length=1, max_length=128, description="盲盒标题")
    description: Optional[str] = Field(None, max_length=1024, description="盲盒描述")
    cover_image: Optional[str] = Field(None, max_length=512, description="封面图片URL")
    box_type: Optional[str] = Field(None, description="盲盒类型")
    original_price: Optional[Decimal] = Field(None, gt=0, description="原价")
    sale_price: Optional[Decimal] = Field(None, gt=0, description="售价")
    stock: Optional[int] = Field(None, ge=0, description="库存数量")
    pickup_start_time: Optional[datetime] = Field(None, description="可取餐开始时间")
    pickup_end_time: Optional[datetime] = Field(None, description="可取餐结束时间")
    status: Optional[int] = Field(None, description="盲盒状态: 1=上架, 0=下架")
    tags: Optional[list[str]] = Field(None, description="标签列表")


# ──────────────────────────── 盲盒查询 ────────────────────────────


class BoxListQuery(BaseModel):
    """盲盒列表查询参数"""

    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=10, ge=1, le=50, description="每页数量")
    box_type: Optional[str] = Field(None, description="盲盒类型筛选")
    min_price: Optional[Decimal] = Field(None, description="最低价格筛选")
    max_price: Optional[Decimal] = Field(None, description="最高价格筛选")
    tag: Optional[str] = Field(None, description="标签筛选")
    sort: Optional[str] = Field(
        default="default",
        description="排序方式: default=默认, price_asc=价格升序, price_desc=价格降序, distance=距离最近",
    )
    lat: Optional[float] = Field(None, description="用户纬度（按距离排序时必填）")
    lng: Optional[float] = Field(None, description="用户经度（按距离排序时必填）")
    radius: Optional[float] = Field(None, ge=0, description="搜索半径（米），不填则不限制")


# ──────────────────────────── 盲盒响应 ────────────────────────────


class BoxTagResponse(BaseModel):
    """盲盒标签"""

    id: int
    tag_name: str

    model_config = {"from_attributes": True}


class BoxResponse(BaseModel):
    """盲盒完整信息响应"""

    id: int
    merchant_id: int
    title: str
    description: Optional[str] = None
    cover_image: Optional[str] = None
    box_type: str
    original_price: Decimal
    sale_price: Decimal
    stock: int
    sold_count: int = Field(default=0, description="已售数量")
    pickup_start_time: Optional[datetime] = None
    pickup_end_time: Optional[datetime] = None
    status: int = Field(default=1, description="盲盒状态")
    store_name: Optional[str] = Field(None, description="商家名称")
    store_logo: Optional[str] = Field(None, description="商家Logo")
    tags: list[BoxTagResponse] = Field(default_factory=list, description="标签列表")
    distance: Optional[float] = Field(None, description="距离（米），查询时传入经纬度则计算返回")
    created_at: datetime

    model_config = {"from_attributes": True}
