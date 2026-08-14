"""
商家端 API 端点

所有接口均需商家登录态（通过 get_current_merchant 依赖注入）。
提供以下接口：
- POST   /merchant/boxes              发布盲盒
- GET    /merchant/boxes              我的盲盒列表
- PUT    /merchant/boxes/{id}          编辑盲盒
- DELETE /merchant/boxes/{id}          下架盲盒
- GET    /merchant/orders             商家订单列表
- PUT    /merchant/orders/{id}/confirm 确认订单
- PUT    /merchant/orders/{id}/ready   备货完成
- GET    /merchant/reviews            评价管理
- GET    /merchant/revenue            收益统计
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_merchant, get_db
from app.models.merchant import Merchant
from app.models.mystery_box import MysteryBox
from app.models.order import Order
from app.models.review import Review
from app.models.user import User
from app.schemas.mystery_box import BoxCreate, BoxUpdate
from app.services.box_service import (
    create_box,
    delete_box,
    get_merchant_boxes,
    update_box,
)
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()


# ──────────────────────────── 辅助：从 JWT payload 获取商家 ORM 对象 ────────────────────────────


def _get_merchant_orm(
    current_merchant_payload: dict = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> Merchant:
    """
    从 JWT payload 中提取商家 ID，查询并返回 Merchant ORM 对象。
    同时校验商家状态。
    """
    merchant_id = int(current_merchant_payload["sub"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商家不存在",
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
    return merchant


# ──────────────────────────── 辅助：WebSocket 推送 ────────────────────────────


async def _notify_order_update(request: Request, order_id: int, data: dict):
    """通过 WebSocket 推送订单状态变更通知（供商家出餐等操作使用）"""
    import logging
    try:
        manager = request.app.state.websocket_manager
        await manager.send_order_update(str(order_id), data)
    except Exception as e:
        logging.getLogger(__name__).error(f"WebSocket 订单推送失败 order_id={order_id}: {e}")


# ──────────────────────────── 发布盲盒 ────────────────────────────


@router.post("/merchant/boxes", status_code=status.HTTP_201_CREATED, summary="发布盲盒")
def create_merchant_box(
    data: BoxCreate,
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    商家发布一个新的盲盒商品。

    创建成功后自动上架（status=1），同时创建关联的标签记录。
    """
    # 业务校验：售价不能高于原价
    if float(data.sale_price) > float(data.original_price):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="售价不能高于原价",
        )

    # 校验盲盒类型
    valid_box_types = {"surplus", "group_buy", "surprise"}
    if data.box_type not in valid_box_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的盲盒类型，允许的类型: {', '.join(sorted(valid_box_types))}",
        )

    box = create_box(merchant_id=merchant.id, data=data, db=db)

    # 构建响应
    return success_response(
        data={
            "id": box.id,
            "merchant_id": box.merchant_id,
            "title": box.title,
            "box_type": box.box_type,
            "original_price": box.original_price,
            "sale_price": box.sale_price,
            "stock": box.stock,
            "status": box.status,
            "created_at": box.created_at,
        },
        message="盲盒发布成功",
    )


# ──────────────────────────── 我的盲盒列表 ────────────────────────────


@router.get("/merchant/boxes", summary="我的盲盒列表")
def list_merchant_boxes(
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    获取当前商家所有的盲盒列表（包含已下架的）。
    按创建时间倒序排列。
    """
    boxes = get_merchant_boxes(merchant_id=merchant.id, db=db)
    return success_response(data=boxes)


# ──────────────────────────── 编辑盲盒 ────────────────────────────


@router.put("/merchant/boxes/{box_id}", summary="编辑盲盒")
def update_merchant_box(
    box_id: int,
    data: BoxUpdate,
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    编辑指定盲盒的信息（仅限本人的盲盒）。
    所有字段均为可选，仅更新传入的字段。
    """
    # 售价与原价校验
    if (data.sale_price is not None and data.original_price is not None
            and float(data.sale_price) > float(data.original_price)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="售价不能高于原价",
        )
    # 仅提供售价时，需读取原价做校验
    if data.sale_price is not None:
        existing_box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
        if existing_box:
            original = float(data.original_price) if data.original_price is not None else existing_box.original_price
            if float(data.sale_price) > original:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="售价不能高于原价",
                )

    try:
        box = update_box(box_id=box_id, merchant_id=merchant.id, data=data, db=db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if "不存在" not in str(e)
            else status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # 构建响应
    tags = box.tags.all() if hasattr(box.tags, 'all') else []
    return success_response(
        data={
            "id": box.id,
            "merchant_id": box.merchant_id,
            "title": box.title,
            "description": box.description,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
            "original_price": box.original_price,
            "sale_price": box.sale_price,
            "stock": box.stock,
            "status": box.status,
            "tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags],
            "updated_at": box.updated_at,
        },
        message="盲盒更新成功",
    )


# ──────────────────────────── 下架盲盒 ────────────────────────────


@router.delete("/merchant/boxes/{box_id}", summary="下架盲盒")
def delete_merchant_box(
    box_id: int,
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    下架指定盲盒（软删除，将状态设为 0）。

    下架后该盲盒将不再出现在公开列表和推荐中。
    """
    try:
        delete_box(box_id=box_id, merchant_id=merchant.id, db=db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if "不存在" not in str(e)
            else status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return success_response(message="盲盒已下架")


# ──────────────────────────── 商家订单列表 ────────────────────────────


@router.get("/merchant/orders", summary="商家订单列表")
def list_merchant_orders(
    order_status: Optional[str] = Query(
        None,
        description="订单状态筛选: pending_pay/paid/confirmed/preparing/ready_pickup/"
                    "delivering/delivered/completed/cancelled/refunding/refunded",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    获取当前商家所有盲盒的订单列表。

    查询逻辑：先查出该商家的所有盲盒ID，再查询这些盲盒的订单。
    支持按订单状态筛选和分页。
    """
    # 获取该商家的所有盲盒ID
    box_ids_subquery = (
        db.query(MysteryBox.id)
        .filter(MysteryBox.merchant_id == merchant.id)
        .subquery()
    )

    # 查询订单
    q = db.query(Order).filter(Order.box_id.in_(box_ids_subquery))

    if order_status:
        # 支持逗号分隔的多状态筛选（如 paid,preparing 表示待处理）
        statuses = [s.strip() for s in order_status.split(",") if s.strip()]
        if len(statuses) == 1:
            q = q.filter(Order.order_status == statuses[0])
        else:
            q = q.filter(Order.order_status.in_(statuses))

    total = q.count()

    orders = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for order in orders:
        # 获取关联盲盒信息
        box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
        box_title = box.title if box else "未知盲盒"

        # 获取用户信息
        user = db.query(User).filter(User.id == order.user_id).first()
        user_phone = user.phone if user else "未知用户"
        user_nickname = user.nickname if user else None

        items.append({
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "user_phone": user_phone,
            "user_nickname": user_nickname,
            "box_id": order.box_id,
            "box_title": box_title,
            "quantity": order.quantity,
            "unit_price": order.unit_price,
            "total_amount": order.total_amount,
            "paid_amount": order.paid_amount,
            "order_status": order.order_status,
            "group_id": order.group_id,
            "group_role": order.group_role,
            "created_at": order.created_at,
            "paid_at": order.paid_at,
            "confirmed_at": order.confirmed_at,
            "delivered_at": order.delivered_at,
            "completed_at": order.completed_at,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 确认订单 ────────────────────────────


@router.put("/merchant/orders/{order_id}/confirm", summary="确认订单")
def confirm_order(
    order_id: int,
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    商家确认订单（接单）。

    将订单状态从 'paid'（已支付）变更为 'confirmed'（已确认）。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在",
        )

    # 权限校验：该订单的盲盒是否属于当前商家
    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if not box or box.merchant_id != merchant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作该订单",
        )

    # 状态校验：只有已支付状态的订单才能确认
    if order.order_status != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前订单状态为'{order.order_status}'，无法确认",
        )

    order.order_status = "confirmed"
    order.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    return success_response(
        message="订单已确认",
        data={"order_id": order.id, "order_status": order.order_status},
    )


# ──────────────────────────── 备货完成 ────────────────────────────


@router.put("/merchant/orders/{order_id}/ready", summary="备货完成")
async def ready_order(
    order_id: int,
    request: Request,
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    商家标记出餐，订单进入待送达状态。

    将订单状态从 'preparing'（配送员已接单）变更为 'ready_pickup'（已出餐待送达）。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在",
        )

    # 权限校验
    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if not box or box.merchant_id != merchant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作该订单",
        )

    # 状态校验：配送员接单后（preparing）商家才能出餐
    if order.order_status != "preparing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前订单状态为'{order.order_status}'，无法标记出餐。请等待配送员接单",
        )

    order.order_status = "ready_pickup"

    # 通知配送员：商家已出餐（群聊消息）
    from app.models.order import DeliveryOrder as DeliveryOrderModel
    from app.models.message import Message
    delivery_order = (
        db.query(DeliveryOrderModel)
        .filter(DeliveryOrderModel.order_id == order_id)
        .first()
    )
    merchant_name = merchant.nickname or merchant.store_name
    if delivery_order:
        # 发群聊消息（所有参与者可见）
        group_msg = Message(
            sender_id=merchant.id,
            sender_role="merchant",
            receiver_id=0,
            receiver_role="all",
            order_id=order_id,
            content=f"🍱 {merchant_name}已出餐，请尽快前往取餐并送达。",
            message_type="system",
        )
        db.add(group_msg)
    else:
        # 尚无骑手接单，仍需通知（后续骑手接单后能看到）
        group_msg = Message(
            sender_id=merchant.id,
            sender_role="merchant",
            receiver_id=0,
            receiver_role="all",
            order_id=order_id,
            content=f"🍱 {merchant_name}已出餐，等待骑手接单取餐。",
            message_type="system",
        )
        db.add(group_msg)

    db.commit()

    # WebSocket 推送：商家已出餐，订单进入待取餐
    await _notify_order_update(request, order_id, {
        "type": "order_ready",
        "order_id": order_id,
        "newStatus": "ready_pickup",
        "order_status": "ready_pickup",
    })

    return success_response(
        message="备货完成，等待取餐",
        data={"order_id": order.id, "order_status": order.order_status},
    )


# ──────────────────────────── 评价管理 ────────────────────────────


@router.get("/merchant/reviews", summary="评价管理")
def list_merchant_reviews(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="按评分筛选"),
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    查看当前商家所有盲盒收到的评价。

    支持按评分筛选和分页。
    """
    # 获取该商家的所有盲盒ID
    box_ids_subquery = (
        db.query(MysteryBox.id)
        .filter(MysteryBox.merchant_id == merchant.id)
        .subquery()
    )

    q = db.query(Review).filter(Review.box_id.in_(box_ids_subquery))

    if rating is not None:
        q = q.filter(Review.rating == rating)

    total = q.count()

    reviews = (
        q.order_by(Review.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for review in reviews:
        # 获取关联盲盒标题
        box = db.query(MysteryBox).filter(MysteryBox.id == review.box_id).first()
        box_title = box.title if box else "未知盲盒"

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
            "user_nickname": user_nickname,
            "box_id": review.box_id,
            "box_title": box_title,
            "rating": review.rating,
            "content": review.content,
            "images": review.images or [],
            "is_anonymous": review.is_anonymous,
            "status": review.status,
            "created_at": review.created_at,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 收益统计 ────────────────────────────


@router.get("/merchant/revenue", summary="收益统计")
def merchant_revenue(
    merchant: Merchant = Depends(_get_merchant_orm),
    db: Session = Depends(get_db),
):
    """
    获取当前商家的收益统计。

    统计维度：
    - 当日：今天 0 时至今
    - 本周：本周一 0 时至今
    - 本月：本月 1 日 0 时至今

    每个维度返回已完成/已支付/配送中等已收款状态的订单数和总金额（含退款）。
    """
    now = datetime.now(timezone.utc)

    # 获取该商家的所有盲盒ID
    box_ids_subquery = (
        db.query(MysteryBox.id)
        .filter(MysteryBox.merchant_id == merchant.id)
        .subquery()
    )

    # 已收款状态列表（排除待支付、已取消、退款中、已退款）
    paid_statuses = ["paid", "confirmed", "preparing", "ready_pickup", "delivering", "delivered", "completed"]

    # 辅助函数：统计指定时间段内的订单数和金额
    def calc_period(start_time: datetime) -> dict:
        q = (
            db.query(Order)
            .filter(
                Order.box_id.in_(box_ids_subquery),
                Order.created_at >= start_time,
                Order.created_at <= now,
                Order.order_status.in_(paid_statuses),
            )
        )
        order_count = q.count()
        total_amount = db.query(func.sum(Order.paid_amount)).filter(
            Order.box_id.in_(box_ids_subquery),
            Order.created_at >= start_time,
            Order.created_at <= now,
            Order.order_status.in_(paid_statuses),
        ).scalar() or 0.0

        return {
            "order_count": order_count,
            "total_amount": round(float(total_amount), 2),
        }

    # 本日：从今天 0 时开始
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_data = calc_period(today_start)

    # 本周：从本周一 0 时开始
    days_since_monday = now.weekday()  # 0=周一, 6=周日
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    week_data = calc_period(week_start)

    # 本月：从本月 1 日 0 时开始
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_data = calc_period(month_start)

    return success_response(
        data={
            "today": today_data,
            "this_week": week_data,
            "this_month": month_data,
            "period_info": {
                "today_start": today_start.isoformat(),
                "week_start": week_start.isoformat(),
                "month_start": month_start.isoformat(),
                "now": now.isoformat(),
            },
        }
    )


# ──────────────────────────── 商家更新个人信息 ────────────────────────────

from pydantic import BaseModel, Field


class MerchantProfileUpdate(BaseModel):
    """商家个人信息更新请求"""
    nickname: str | None = Field(None, max_length=50, description="商家昵称")
    avatar_url: str | None = Field(None, max_length=500, description="头像URL")


@router.put("/merchant/me", summary="更新商家个人信息")
def update_merchant_profile(
    req: MerchantProfileUpdate,
    current_merchant_payload: dict = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """更新当前登录商家的昵称和头像"""
    merchant = _get_merchant_orm(current_merchant_payload, db)

    if req.nickname is not None:
        merchant.nickname = req.nickname
    if req.avatar_url is not None:
        merchant.avatar_url = req.avatar_url

    db.commit()
    db.refresh(merchant)

    return success_response(
        data={
            "id": merchant.id,
            "phone": merchant.phone,
            "store_name": merchant.store_name,
            "nickname": merchant.nickname,
            "avatar_url": merchant.avatar_url,
        },
        message="个人信息已更新",
    )


@router.get("/merchant/me/balance", summary="查询商家余额")
def get_merchant_balance(
    merchant: Merchant = Depends(_get_merchant_orm),
):
    """查询当前商家账户余额"""
    return success_response(data={"balance": merchant.balance})
