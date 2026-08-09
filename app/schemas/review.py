"""
评价相关 Schema —— 创建、响应
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    """创建评价请求"""

    order_id: int = Field(..., gt=0, description="订单ID")
    rating: int = Field(..., ge=1, le=5, description="评分（1~5 星）")
    content: Optional[str] = Field(None, max_length=1024, description="评价内容")
    images: Optional[list[str]] = Field(default_factory=list, max_length=9, description="评价图片URL列表（最多9张）")
    is_anonymous: bool = Field(default=False, description="是否匿名评价")


class ReviewResponse(BaseModel):
    """评价响应"""

    id: int
    order_id: int
    user_id: int
    box_id: int
    rating: int
    content: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    is_anonymous: bool
    status: int = Field(default=1, description="评价状态: 1=显示, 0=隐藏")
    user_nickname: Optional[str] = Field(None, description="用户昵称（匿名时显示'匿名用户'）")
    created_at: datetime

    model_config = {"from_attributes": True}
