"""
评价业务逻辑模块

包含：
- 创建评价（校验订单归属、订单状态、是否已评价）
- 查询盲盒评价列表
- 查询用户评价列表
- 管理端隐藏评价
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.order import Order
from app.models.mystery_box import MysteryBox
from app.models.user import User
from app.schemas.review import ReviewCreate


def create_review(user_id: int, data: ReviewCreate, db: Session) -> Review:
    """
    创建评价。

    校验流程：
    1. 检查订单是否存在且属于该用户
    2. 检查订单状态是否为 completed
    3. 检查该订单是否已经评价过（一个订单只能评价一次）
    4. 创建评价记录
    5. 更新盲盒的平均评分（重新计算所有评价的平均值）

    Args:
        user_id: 当前登录用户 ID
        data:   评价创建数据（order_id, rating, content, images, is_anonymous）
        db:     数据库会话

    Returns:
        新创建的 Review 对象

    Raises:
        ValueError: 校验失败时抛出
    """
    # 1. 检查订单是否存在且属于该用户
    order = db.query(Order).filter(
        Order.id == data.order_id,
        Order.user_id == user_id,
    ).first()

    if not order:
        raise ValueError("订单不存在")

    # 2. 检查订单状态是否为 completed
    if order.order_status != "completed":
        raise ValueError("只有已完成的订单才能评价")

    # 3. 检查该订单是否已经评价过
    existing_review = db.query(Review).filter(
        Review.order_id == data.order_id
    ).first()

    if existing_review:
        raise ValueError("该订单已评价，不能重复评价")

    # 4. 创建评价记录
    review = Review(
        order_id=data.order_id,
        user_id=user_id,
        box_id=order.box_id,
        rating=data.rating,
        content=data.content,
        images=data.images or [],
        is_anonymous=data.is_anonymous,
        status=1,  # 1=正常显示
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # 5. 更新盲盒的平均评分
    _update_box_rating_avg(order.box_id, db)

    return review


def _update_box_rating_avg(box_id: int, db: Session) -> None:
    """
    重新计算并更新盲盒的平均评分。

    统计该盲盒下所有 status=1（正常显示）的评价的 rating 平均值，
    更新 mystery_box 表的 rating_avg 字段。

    Args:
        box_id: 盲盒 ID
        db:     数据库会话
    """
    result = db.query(
        func.avg(Review.rating).label("avg_rating"),
        func.count(Review.id).label("review_count"),
    ).filter(
        Review.box_id == box_id,
        Review.status == 1,
    ).first()

    avg_rating = round(float(result.avg_rating), 1) if result.avg_rating else 0.0

    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if box:
        box.rating_avg = avg_rating
        db.commit()


def get_box_reviews(
    box_id: int,
    page: int = 1,
    size: int = 20,
    db: Session = None,
) -> tuple[list[dict], int]:
    """
    获取指定盲盒的评价列表（分页）。

    只返回 status=1（正常）的评价。
    评价列表按创建时间倒序排列。

    Args:
        box_id: 盲盒 ID
        page:   页码，从 1 开始
        size:   每页条数
        db:     数据库会话

    Returns:
        (评价列表, 总条数) 元组
    """
    # 构建基础查询
    base_query = db.query(Review).filter(
        Review.box_id == box_id,
        Review.status == 1,
    )

    total = base_query.count()

    reviews = (
        base_query
        .order_by(Review.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # 组装返回数据，含用户昵称
    items = []
    for review in reviews:
        user = db.query(User).filter(User.id == review.user_id).first()
        user_nickname = "匿名用户" if review.is_anonymous else (
            user.nickname if user else f"用户{review.user_id}"
        )
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

    return items, total


def get_user_reviews(
    user_id: int,
    page: int = 1,
    size: int = 20,
    db: Session = None,
) -> tuple[list[dict], int]:
    """
    获取指定用户的评价列表（分页）。

    包含所有 status（正常和隐藏），用户可以看到自己的全部评价。
    评价列表按创建时间倒序排列。

    Args:
        user_id: 用户 ID
        page:    页码，从 1 开始
        size:    每页条数
        db:      数据库会话

    Returns:
        (评价列表, 总条数) 元组
    """
    base_query = db.query(Review).filter(
        Review.user_id == user_id,
    )

    total = base_query.count()

    reviews = (
        base_query
        .order_by(Review.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for review in reviews:
        # 获取盲盒标题（用于展示）
        box = db.query(MysteryBox).filter(MysteryBox.id == review.box_id).first()
        items.append({
            "id": review.id,
            "order_id": review.order_id,
            "user_id": review.user_id,
            "box_id": review.box_id,
            "box_title": box.title if box else "已下架",
            "box_cover": box.cover_image if box else "",
            "rating": review.rating,
            "content": review.content,
            "images": review.images or [],
            "is_anonymous": review.is_anonymous,
            "status": review.status,
            "created_at": review.created_at,
        })

    return items, total


def hide_review(review_id: int, db: Session) -> Review:
    """
    管理端隐藏评价（将 status 设为 0）。

    隐藏后该评价不再在盲盒详情页展示，且不计入评分统计。

    Args:
        review_id: 评价 ID
        db:        数据库会话

    Returns:
        更新后的 Review 对象

    Raises:
        ValueError: 评价不存在时抛出
    """
    review = db.query(Review).filter(Review.id == review_id).first()

    if not review:
        raise ValueError("评价不存在")

    review.status = 0
    db.commit()
    db.refresh(review)

    # 重新计算盲盒平均评分（排除已隐藏的评价）
    _update_box_rating_avg(review.box_id, db)

    return review
