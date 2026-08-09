"""
盲盒 API 端点（公开接口）

提供以下接口：
- GET  /boxes            盲盒列表（公开，支持筛选排序分页）
- GET  /boxes/nearby     附近盲盒（根据坐标和半径）
- GET  /boxes/recommend  推荐盲盒（需登录，基于用户偏好算法推荐）
- GET  /boxes/{id}       盲盒详情（自动增加浏览次数）
- GET  /boxes/{id}/reviews  盲盒评价列表
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.mystery_box import MysteryBox
from app.models.review import Review
from app.models.user import User
from app.schemas.mystery_box import BoxListQuery
from app.services.box_service import (
    get_box_detail,
    get_box_list,
    get_nearby_boxes,
    increment_view_count,
)
from app.services.matching_service import recommend_boxes
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()


# ──────────────────────────── 盲盒列表（公开） ────────────────────────────


@router.get("/boxes", summary="盲盒列表")
def list_boxes(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    box_type: Optional[str] = Query(None, description="盲盒类型: surplus/group_buy/surprise"),
    min_price: Optional[float] = Query(None, description="最低价格"),
    max_price: Optional[float] = Query(None, description="最高价格"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    sort: Optional[str] = Query(
        default="default",
        description="排序方式: default/price_asc/price_desc/distance/rating/sales",
    ),
    lat: Optional[float] = Query(None, description="用户纬度（距离排序时使用）"),
    lng: Optional[float] = Query(None, description="用户经度（距离排序时使用）"),
    radius: Optional[float] = Query(None, ge=0, description="搜索半径（米）"),
    db: Session = Depends(get_db),
):
    """
    盲盒列表接口（公开访问）。

    支持按类型、价格区间、标签筛选，支持多种排序方式和分页。
    传入经纬度时自动计算每个盲盒与用户的距离。
    """
    query_params = BoxListQuery(
        page=page,
        size=size,
        box_type=box_type,
        min_price=min_price,
        max_price=max_price,
        tag=tag,
        sort=sort,
        lat=lat,
        lng=lng,
        radius=radius,
    )
    items, total = get_box_list(query_params, db)
    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 附近盲盒 ────────────────────────────


@router.get("/boxes/nearby", summary="附近盲盒")
def nearby_boxes(
    lat: float = Query(..., description="当前纬度"),
    lng: float = Query(..., description="当前经度"),
    radius: int = Query(default=3000, ge=100, le=50000, description="搜索半径（米）"),
    box_type: Optional[str] = Query(None, description="盲盒类型筛选"),
    limit: int = Query(default=20, ge=1, le=50, description="返回数量上限"),
    db: Session = Depends(get_db),
):
    """
    获取指定坐标附近的盲盒列表。

    按距离由近到远排序，自动过滤超出半径范围的盲盒。
    """
    items = get_nearby_boxes(
        lat=lat,
        lng=lng,
        radius=radius,
        db=db,
        box_type=box_type,
        limit=limit,
    )
    return success_response(data=items)


# ──────────────────────────── 推荐盲盒（需登录） ────────────────────────────


@router.get("/boxes/recommend", summary="推荐盲盒")
def recommend(
    lat: float = Query(..., description="当前纬度"),
    lng: float = Query(..., description="当前经度"),
    radius: int = Query(default=5000, ge=100, le=50000, description="推荐半径（米）"),
    limit: int = Query(default=20, ge=1, le=50, description="返回数量上限"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    基于用户偏好和历史行为的个性化盲盒推荐。

    需登录态，采用五维混合推荐算法：
    - 标签匹配（30%）：用户偏好标签与盲盒标签的加权 Jaccard 相似度
    - 距离分（25%）：距离越近得分越高
    - 评分分（20%）：盲盒平均评分归一化
    - 热门度（15%）：销量对数归一化
    - 价格匹配（10%）：与用户历史均价偏差归一化
    """
    user_id = int(current_user["sub"])
    results = recommend_boxes(
        user_id=user_id,
        lat=lat,
        lng=lng,
        radius=radius,
        limit=limit,
        db=db,
    )
    return success_response(data=results)


# ──────────────────────────── 盲盒详情 ────────────────────────────


@router.get("/boxes/{box_id}", summary="盲盒详情")
def box_detail(
    box_id: int,
    lat: Optional[float] = Query(None, description="用户纬度（可选，用于计算距离）"),
    lng: Optional[float] = Query(None, description="用户经度（可选，用于计算距离）"),
    db: Session = Depends(get_db),
):
    """
    获取盲盒详情。

    - 返回盲盒完整信息，包含商家名称和标签列表
    - 可选传入经纬度以计算距离
    - 自动增加该盲盒的浏览次数
    """
    detail = get_box_detail(box_id=box_id, db=db, lat=lat, lng=lng)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="盲盒不存在",
        )
    # 自动增加浏览次数
    increment_view_count(box_id, db)
    return success_response(data=detail)


# ──────────────────────────── 盲盒评价列表 ────────────────────────────


@router.get("/boxes/{box_id}/reviews", summary="盲盒评价列表")
def box_reviews(
    box_id: int,
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    db: Session = Depends(get_db),
):
    """
    获取指定盲盒的评价列表。

    返回正常显示的评价（status=1），包含用户昵称（匿名评价显示"匿名用户"）。
    """
    # 校验盲盒存在
    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="盲盒不存在",
        )

    total = (
        db.query(Review)
        .filter(Review.box_id == box_id, Review.status == 1)
        .count()
    )

    reviews = (
        db.query(Review)
        .filter(Review.box_id == box_id, Review.status == 1)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for review in reviews:
        # 获取用户昵称
        user_nickname = "匿名用户"
        if not review.is_anonymous:
            user = db.query(User).filter(User.id == review.user_id).first()
            if user:
                user_nickname = user.nickname or f"用户{user.phone[-4:] if user.phone else review.user_id}"

        items.append({
            "id": review.id,
            "order_id": review.order_id,
            "user_id": review.user_id,
            "box_id": review.box_id,
            "rating": review.rating,
            "content": review.content,
            "images": review.images or [],
            "is_anonymous": review.is_anonymous,
            "status": review.status,
            "user_nickname": user_nickname,
            "created_at": review.created_at,
        })

    return paginated_response(items=items, total=total, page=page, size=size)
