"""外卖盲盒 - 抽卡系统 API 端点

提供以下接口：
- POST   /draw          执行抽卡（需登录）
- GET    /draw/history   抽卡历史（需登录，分页）
- GET    /draw/stats     抽卡统计数据（需登录）
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.services.draw_service import draw_box, get_draw_history, get_user_draw_stats
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()


class DrawRequest(BaseModel):
    min_price: Optional[float] = Field(None, ge=0, description="最低价格筛选")
    max_price: Optional[float] = Field(None, ge=0, description="最高价格筛选")
    tags: Optional[str] = Field(None, description="标签筛选，多个用逗号分隔")
    city: Optional[str] = Field(None, description="城市筛选")


# ──────────────────────────── 执行抽卡 ────────────────────────────

@router.post("/draw", summary="执行抽卡")
def execute_draw(
    body: DrawRequest = DrawRequest(),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格筛选"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格筛选"),
    tags: Optional[str] = Query(None, description="标签筛选，多个用逗号分隔"),
    city: Optional[str] = Query(None, description="城市筛选"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 优先使用body参数，fallback到query参数
    min_price = body.min_price if body.min_price is not None else min_price
    max_price = body.max_price if body.max_price is not None else max_price
    tags = body.tags if body.tags is not None else tags
    city = body.city if body.city is not None else city
    """
    执行一次抽卡操作。

    抽卡算法：
    - 按稀有度概率随机: SSR=3%, SR=12%, R=25%, N=60%
    - 从对应稀有度盲盒池中随机选一个
    - 如果该稀有度池为空，自动降级到下一稀有度
    - 返回模糊描述（不含具体餐品内容），仅含类型标签、价格、稀有度、梗文案
    - 每日前3次为免费展示，超出返回提示信息
    """
    user_id = int(current_user["sub"])

    # 解析筛选条件
    filters = {}
    if min_price is not None:
        filters["min_price"] = min_price
    if max_price is not None:
        filters["max_price"] = max_price
    if tags:
        filters["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if city:
        filters["city"] = city

    try:
        result = draw_box(user_id=user_id, filters=filters, db=db)
    except ValueError as e:
        return error_response(code=2001, message=str(e))

    return success_response(data=result, message=result.get("meme_text", "抽卡成功"))


# ──────────────────────────── 抽卡历史 ────────────────────────────

@router.get("/draw/history", summary="抽卡历史")
def draw_history(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的抽卡历史记录（分页）。

    按抽卡时间倒序排列，返回稀有度、梗文案、关联盲盒信息等。
    """
    user_id = int(current_user["sub"])
    items, total = get_draw_history(user_id=user_id, page=page, size=size, db=db)
    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 抽卡统计 ────────────────────────────

@router.get("/draw/stats", summary="抽卡统计")
def draw_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的抽卡统计数据。

    包含: 总抽卡次数、各稀有度数量、幸运值、称号等级、今日剩余免费次数。
    """
    user_id = int(current_user["sub"])
    stats = get_user_draw_stats(user_id=user_id, db=db)
    return success_response(data=stats)
