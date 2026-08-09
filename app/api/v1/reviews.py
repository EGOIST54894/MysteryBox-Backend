"""
评价 API 端点

提供以下接口：
- POST   /reviews           发布评价（需登录）
- GET    /reviews/my        我的评价列表
- GET    /reviews/box/{box_id}  盲盒的评价列表
- PUT    /reviews/{id}/hide 隐藏评价（管理端）
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.schemas.review import ReviewCreate, ReviewResponse
from app.services.review_service import (
    create_review,
    get_box_reviews,
    get_user_reviews,
    hide_review,
)
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()


@router.post("", summary="发布评价")
def create_new_review(
    data: ReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    对已完成的订单进行评价。

    - 需要登录
    - 只有订单所属用户才能评价
    - 订单状态必须为 completed
    - 一个订单只能评价一次
    - 评分范围 1~5 星
    - 可上传最多 9 张图片
    - 可选择是否匿名评价
    """
    try:
        user_id = int(current_user.get("sub"))
        review = create_review(user_id, data, db)

        # 组装响应数据
        review_data = {
            "id": review.id,
            "order_id": review.order_id,
            "user_id": review.user_id,
            "box_id": review.box_id,
            "rating": review.rating,
            "content": review.content,
            "images": review.images or [],
            "is_anonymous": review.is_anonymous,
            "status": review.status,
            "created_at": review.created_at,
        }
        return success_response(data=review_data, message="评价成功")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my", summary="我的评价列表")
def list_my_reviews(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前登录用户的评价列表。

    - 需要登录
    - 支持分页
    - 包含所有状态的评价（正常和已隐藏）
    """
    user_id = int(current_user.get("sub"))
    items, total = get_user_reviews(user_id, page, size, db)
    return paginated_response(items=items, total=total, page=page, size=size)


@router.get("/box/{box_id}", summary="盲盒评价列表")
def list_box_reviews(
    box_id: int,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """
    获取指定盲盒的评价列表。

    - 无需登录，公开访问
    - 只返回状态正常的评价（status=1）
    - 支持分页
    - 匿名评价显示为"匿名用户"
    """
    items, total = get_box_reviews(box_id, page, size, db)
    return paginated_response(items=items, total=total, page=page, size=size)


@router.put("/{review_id}/hide", summary="隐藏评价（管理端）")
def review_hide(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    管理端隐藏评价（将 status 设为 0）。

    - 需要管理员权限
    - 隐藏后评价不再公开展示，且不计入评分统计
    - 用户自己仍可在"我的评价"中看到
    """
    # 校验管理员角色
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，仅管理员可执行此操作",
        )

    try:
        review = hide_review(review_id, db)
        return success_response(message="评价已隐藏")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
