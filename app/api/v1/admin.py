"""
管理后台 API 端点

所有接口均需管理员认证（通过 get_current_admin 依赖注入，JWT role=admin）。
提供以下接口：
- GET  /admin/dashboard              数据看板
- GET  /admin/users                  用户列表（搜索+分页）
- PUT  /admin/users/{id}/status      启用/禁用用户
- GET  /admin/merchants              商家列表（支持审核状态筛选）
- PUT  /admin/merchants/{id}/audit   审核商家
- GET  /admin/delivery               配送员列表
- PUT  /admin/delivery/{id}/audit    审核配送员
- GET  /admin/boxes                  盲盒列表（支持审核筛选）
- PUT  /admin/boxes/{id}/status      盲盒上下架
- GET  /admin/statistics/orders      订单统计（按日期范围+类型）
- GET  /admin/statistics/revenue     营收统计（按日期范围，按天汇总）
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.dependencies import get_current_admin, get_db
from app.models.admin import Admin
from app.models.delivery import DeliveryPersonnel
from app.models.merchant import Merchant
from app.models.mystery_box import MysteryBox
from app.models.order import Order
from app.models.payment import PaymentRecord
from app.models.user import User
from app.utils.response import error_response, paginated_response, success_response

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────── Pydantic 请求模型 ────────────────────────────

class UserStatusUpdate(BaseModel):
    """用户状态更新请求体"""
    status: int = Field(..., ge=0, le=1, description="状态: 0禁用 1启用")


class MerchantAuditRequest(BaseModel):
    """商家审核请求体"""
    status: int = Field(..., ge=1, le=2, description="审核结果: 1通过 2拒绝")
    reject_reason: Optional[str] = Field(None, max_length=500, description="拒绝原因（拒绝时必填）")


class DeliveryAuditRequest(BaseModel):
    """配送员审核请求体"""
    status: int = Field(..., ge=1, le=3, description="审核结果: 1通过(在线) 2拒绝(离线) 3禁用")


class BoxStatusUpdate(BaseModel):
    """盲盒状态更新请求体"""
    status: int = Field(..., ge=0, le=1, description="状态: 0下架 1上架")


# ──────────────────────────── 辅助：从 JWT payload 获取管理员 ORM 对象 ────────────────────────────

def _get_admin_orm(
    current_admin_payload: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Admin:
    """
    从 JWT payload 中提取管理员 ID，查询并返回 Admin ORM 对象。
    同时校验管理员状态。
    """
    admin_id = int(current_admin_payload["sub"])
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="管理员不存在",
        )
    if admin.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账户已被禁用",
        )
    return admin


# ==================== 1. 数据看板 ====================

@router.get("/admin/dashboard", summary="数据看板")
def dashboard(
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    管理后台首页数据看板。

    返回内容：
    - 总数统计：用户、商家、配送员、订单
    - 今日数据：今日订单数、今日营收
    - 待处理：待审核商家数、待审核配送员数
    - 最近订单：最近 10 条订单（含简要信息）
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 总数统计
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_merchants = db.query(func.count(Merchant.id)).scalar() or 0
    total_delivery = db.query(func.count(DeliveryPersonnel.id)).scalar() or 0
    total_orders = db.query(func.count(Order.id)).scalar() or 0

    # 今日数据
    today_orders = (
        db.query(func.count(Order.id))
        .filter(Order.created_at >= today_start)
        .scalar() or 0
    )
    today_revenue = (
        db.query(func.sum(PaymentRecord.pay_amount))
        .filter(
            PaymentRecord.status == "success",
            PaymentRecord.paid_at >= today_start,
        )
        .scalar() or 0.0
    )

    # 待处理
    pending_merchants = (
        db.query(func.count(Merchant.id))
        .filter(Merchant.status == 0)
        .scalar() or 0
    )
    pending_delivery = (
        db.query(func.count(DeliveryPersonnel.id))
        .filter(DeliveryPersonnel.status == 0)
        .scalar() or 0
    )

    # 最近 10 条订单
    recent_orders_query = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )
    recent_orders = []
    for o in recent_orders_query:
        user = db.query(User).filter(User.id == o.user_id).first()
        box = db.query(MysteryBox).filter(MysteryBox.id == o.box_id).first()
        recent_orders.append({
            "id": o.id,
            "order_no": o.order_no,
            "order_status": o.order_status,
            "total_amount": float(o.total_amount),
            "paid_amount": float(o.paid_amount),
            "user_nickname": user.nickname if user else "未知用户",
            "box_title": box.title if box else "未知盲盒",
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })

    return success_response(data={
        "total_users": total_users,
        "total_merchants": total_merchants,
        "total_delivery": total_delivery,
        "total_orders": total_orders,
        "today_orders": today_orders,
        "today_revenue": round(float(today_revenue), 2),
        "pending_merchants": pending_merchants,
        "pending_delivery": pending_delivery,
        "recent_orders": recent_orders,
    })


# ==================== 2. 用户管理 ====================

@router.get("/admin/users", summary="用户列表")
def list_users(
    keyword: Optional[str] = Query(None, description="搜索关键词（手机号/昵称）"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    获取用户列表，支持按手机号或昵称模糊搜索，支持分页。
    """
    q = db.query(User)

    if keyword:
        like_pattern = f"%{keyword}%"
        q = q.filter(
            func.coalesce(User.phone, "").like(like_pattern) |
            func.coalesce(User.nickname, "").like(like_pattern)
        )

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for u in users:
        items.append({
            "id": u.id,
            "phone": u.phone,
            "nickname": u.nickname,
            "avatar_url": u.avatar_url,
            "gender": u.gender,
            "status": u.status,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


@router.put("/admin/users/{user_id}/status", summary="启用/禁用用户")
def update_user_status(
    user_id: int,
    req: UserStatusUpdate,
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    启用或禁用指定用户。

    - status=1: 启用
    - status=0: 禁用
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    user.status = req.status
    db.commit()

    action = "启用" if req.status == 1 else "禁用"
    return success_response(
        message=f"用户已{action}",
        data={"id": user.id, "status": user.status},
    )


# ==================== 3. 商家管理 ====================

@router.get("/admin/merchants", summary="商家列表")
def list_merchants(
    audit_status: Optional[int] = Query(
        None, ge=0, le=3,
        description="审核状态筛选: 0待审核 1通过 2拒绝 3禁用",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    获取商家列表，支持按审核状态筛选，支持分页。
    """
    q = db.query(Merchant)

    if audit_status is not None:
        q = q.filter(Merchant.status == audit_status)

    total = q.count()
    merchants = q.order_by(Merchant.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for m in merchants:
        # 统计该商家盲盒数和订单数
        box_count = db.query(func.count(MysteryBox.id)).filter(MysteryBox.merchant_id == m.id).scalar() or 0
        items.append({
            "id": m.id,
            "phone": m.phone,
            "store_name": m.store_name,
            "category": m.category,
            "description": m.description,
            "status": m.status,
            "latitude": float(m.latitude) if m.latitude else None,
            "longitude": float(m.longitude) if m.longitude else None,
            "district": m.district,
            "address_detail": m.address_detail,
            "rating_avg": float(m.rating_avg) if m.rating_avg else 0.0,
            "box_count": box_count,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


@router.put("/admin/merchants/{merchant_id}/audit", summary="审核商家")
def audit_merchant(
    merchant_id: int,
    req: MerchantAuditRequest,
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    审核指定商家。

    - status=1: 审核通过
    - status=2: 审核拒绝（需填写拒绝原因）

    被拒绝的商家可以看到拒绝原因。
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商家不存在",
        )

    # 校验：只有待审核（status=0）的商家才能审核
    if merchant.status != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前商家状态为 {merchant.status}，无法审核（仅可审核待审核状态的商家）",
        )

    # 拒绝时必须填写原因
    if req.status == 2 and not req.reject_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="拒绝时必须填写拒绝原因",
        )

    merchant.status = req.status
    # 如果有拒绝原因，可以存储在 description 字段后追加，或记录到日志
    if req.reject_reason:
        logger.info(f"商家 {merchant.store_name}(id={merchant_id}) 被拒绝，原因: {req.reject_reason}")

    db.commit()

    action = "通过" if req.status == 1 else "拒绝"
    return success_response(
        message=f"商家审核已{action}",
        data={
            "id": merchant.id,
            "store_name": merchant.store_name,
            "status": merchant.status,
            "reject_reason": req.reject_reason if req.status == 2 else None,
        },
    )


# ==================== 4. 配送员管理 ====================

@router.get("/admin/delivery", summary="配送员列表")
def list_delivery(
    audit_status: Optional[int] = Query(
        None, ge=0, le=3,
        description="状态筛选: 0待审核 1在线 2离线 3禁用",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    获取配送员列表，支持按状态筛选，支持分页。
    """
    q = db.query(DeliveryPersonnel)

    if audit_status is not None:
        q = q.filter(DeliveryPersonnel.status == audit_status)

    total = q.count()
    delivery_list = q.order_by(DeliveryPersonnel.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for dp in delivery_list:
        items.append({
            "id": dp.id,
            "phone": dp.phone,
            "real_name": dp.real_name,
            "id_card": dp.id_card[:6] + "****" + dp.id_card[-4:],  # 身份证脱敏
            "status": dp.status,
            "current_lat": float(dp.current_lat) if dp.current_lat else None,
            "current_lng": float(dp.current_lng) if dp.current_lng else None,
            "rating_avg": float(dp.rating_avg) if dp.rating_avg else 0.0,
            "completed_orders": dp.completed_orders,
            "created_at": dp.created_at.isoformat() if dp.created_at else None,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


@router.put("/admin/delivery/{delivery_id}/audit", summary="审核配送员")
def audit_delivery(
    delivery_id: int,
    req: DeliveryAuditRequest,
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    审核指定配送员。

    - status=1: 审核通过（设为在线状态）
    - status=2: 设为离线（不通过审核）
    - status=3: 禁用
    """
    dp = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.id == delivery_id).first()
    if not dp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配送员不存在",
        )

    # 校验：只有待审核状态的配送员才能审核
    if dp.status != 0 and req.status == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前配送员状态为 {dp.status}，无法审核（仅可审核待审核状态的配送员）",
        )

    dp.status = req.status
    db.commit()

    status_map = {1: "审核通过(在线)", 2: "已设为离线", 3: "已禁用"}
    action = status_map.get(req.status, f"状态已更新为{req.status}")
    return success_response(
        message=f"配送员{action}",
        data={
            "id": dp.id,
            "real_name": dp.real_name,
            "status": dp.status,
        },
    )


# ==================== 5. 盲盒管理 ====================

@router.get("/admin/boxes", summary="盲盒列表")
def list_boxes(
    box_status: Optional[int] = Query(
        None, ge=0, le=3,
        description="盲盒状态筛选: 0下架 1上架 2售罄 3过期",
    ),
    audit_status: Optional[int] = Query(
        None, ge=0, le=1,
        description="审核筛选: 0待审核(商家未审核) 1已审核(商家已通过)",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    获取盲盒列表，支持按状态和商家审核状态筛选。

    当 audit_status 筛选时，会关联商家表进行过滤：
    - audit_status=0: 仅显示未审核商家发布的盲盒
    - audit_status=1: 仅显示已审核通过商家发布的盲盒
    """
    q = db.query(MysteryBox)

    if box_status is not None:
        q = q.filter(MysteryBox.status == box_status)

    # 按商家的审核状态筛选
    if audit_status is not None:
        merchant_ids_sub = (
            db.query(Merchant.id)
            .filter(Merchant.status == (1 if audit_status == 1 else 0))
            .subquery()
        )
        q = q.filter(MysteryBox.merchant_id.in_(merchant_ids_sub))

    total = q.count()
    boxes = q.order_by(MysteryBox.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for box in boxes:
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        tags = [t.tag_name for t in box.tags.all()]
        items.append({
            "id": box.id,
            "merchant_id": box.merchant_id,
            "merchant_name": merchant.store_name if merchant else "未知商家",
            "title": box.title,
            "description": box.description,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
            "original_price": float(box.original_price),
            "sale_price": float(box.sale_price),
            "stock": box.stock,
            "total_stock": box.total_stock,
            "status": box.status,
            "tags": tags,
            "view_count": box.view_count,
            "sale_count": box.sale_count,
            "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
            "created_at": box.created_at.isoformat() if box.created_at else None,
        })

    return paginated_response(items=items, total=total, page=page, size=size)


@router.put("/admin/boxes/{box_id}/status", summary="盲盒上下架")
def update_box_status(
    box_id: int,
    req: BoxStatusUpdate,
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    上架或下架指定盲盒。

    - status=1: 上架
    - status=0: 下架
    """
    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="盲盒不存在",
        )

    box.status = req.status
    db.commit()

    action = "上架" if req.status == 1 else "下架"
    return success_response(
        message=f"盲盒已{action}",
        data={"id": box.id, "title": box.title, "status": box.status},
    )


# ==================== 6. 订单统计 ====================

@router.get("/admin/statistics/orders", summary="订单统计")
def order_statistics(
    start_date: Optional[str] = Query(
        None, description="开始日期，格式 YYYY-MM-DD，默认 7 天前",
    ),
    end_date: Optional[str] = Query(
        None, description="结束日期，格式 YYYY-MM-DD，默认今天",
    ),
    box_type: Optional[str] = Query(
        None, description="盲盒类型筛选: surplus/group_buy/surprise",
    ),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    按日期范围和盲盒类型统计订单数据。

    返回：
    - 总订单数
    - 各状态订单数
    - 按类型的订单数分布
    - 每日订单数趋势

    默认统计最近 7 天数据。
    """
    now = datetime.now(timezone.utc)

    # 解析日期范围
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date 格式错误，应为 YYYY-MM-DD",
            )
    else:
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date 格式错误，应为 YYYY-MM-DD",
            )
    else:
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # 基础查询条件
    base_filter = [Order.created_at >= start, Order.created_at <= end]

    # 总订单数
    total_orders = db.query(func.count(Order.id)).filter(*base_filter).scalar() or 0

    # 各状态订单数
    status_stats = {}
    all_statuses = [
        "pending_pay", "paid", "confirmed", "preparing", "ready_pickup",
        "delivering", "delivered", "completed", "cancelled",
    ]
    for s in all_statuses:
        count = (
            db.query(func.count(Order.id))
            .filter(Order.order_status == s, *base_filter)
            .scalar() or 0
        )
        status_stats[s] = count

    # 按盲盒类型统计（需关联盲盒表）
    type_stats = {}
    for bt in ["surplus", "group_buy", "surprise"]:
        count = (
            db.query(func.count(Order.id))
            .join(MysteryBox, Order.box_id == MysteryBox.id)
            .filter(MysteryBox.box_type == bt, *base_filter)
            .scalar() or 0
        )
        type_stats[bt] = count

    # 每日订单数趋势
    daily_trend = []
    current_date = start
    while current_date <= end:
        day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 如果指定了盲盒类型，需要关联筛选
        if box_type:
            count_q = (
                db.query(func.count(Order.id))
                .join(MysteryBox, Order.box_id == MysteryBox.id)
                .filter(
                    Order.created_at >= day_start,
                    Order.created_at <= day_end,
                    MysteryBox.box_type == box_type,
                )
            )
        else:
            count_q = (
                db.query(func.count(Order.id))
                .filter(
                    Order.created_at >= day_start,
                    Order.created_at <= day_end,
                )
            )
        count = count_q.scalar() or 0
        daily_trend.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "order_count": count,
        })
        current_date += timedelta(days=1)

    return success_response(data={
        "period": {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
        },
        "total_orders": total_orders,
        "by_status": status_stats,
        "by_box_type": type_stats,
        "daily_trend": daily_trend,
    })


# ==================== 7. 营收统计 ====================

@router.get("/admin/statistics/revenue", summary="营收统计")
def revenue_statistics(
    start_date: Optional[str] = Query(
        None, description="开始日期，格式 YYYY-MM-DD，默认 7 天前",
    ),
    end_date: Optional[str] = Query(
        None, description="结束日期，格式 YYYY-MM-DD，默认今天",
    ),
    admin: Admin = Depends(_get_admin_orm),
    db: Session = Depends(get_db),
):
    """
    按日期范围和天汇总营收数据。

    返回：
    - 总营收（已成功支付的金额总和）
    - 总退款金额
    - 净营收（总营收 - 退款）
    - 每日营收明细（日期、订单数、营收、退款）

    默认统计最近 7 天数据。
    """
    now = datetime.now(timezone.utc)

    # 解析日期范围
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date 格式错误，应为 YYYY-MM-DD",
            )
    else:
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date 格式错误，应为 YYYY-MM-DD",
            )
    else:
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # 总营收（成功支付）
    total_revenue = (
        db.query(func.sum(PaymentRecord.pay_amount))
        .filter(
            PaymentRecord.status == "success",
            PaymentRecord.paid_at >= start,
            PaymentRecord.paid_at <= end,
        )
        .scalar() or 0.0
    )

    # 总退款
    total_refund = (
        db.query(func.sum(PaymentRecord.pay_amount))
        .filter(
            PaymentRecord.status == "refunded",
            PaymentRecord.paid_at >= start,
            PaymentRecord.paid_at <= end,
        )
        .scalar() or 0.0
    )

    net_revenue = round(float(total_revenue) - float(total_refund), 2)

    # 每日营收明细
    daily_details = []
    current_date = start
    while current_date <= end:
        day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 当日营收
        day_revenue = (
            db.query(func.sum(PaymentRecord.pay_amount))
            .filter(
                PaymentRecord.status == "success",
                PaymentRecord.paid_at >= day_start,
                PaymentRecord.paid_at <= day_end,
            )
            .scalar() or 0.0
        )

        # 当日退款
        day_refund = (
            db.query(func.sum(PaymentRecord.pay_amount))
            .filter(
                PaymentRecord.status == "refunded",
                PaymentRecord.paid_at >= day_start,
                PaymentRecord.paid_at <= day_end,
            )
            .scalar() or 0.0
        )

        # 当日成功支付订单数
        day_order_count = (
            db.query(func.count(Order.id))
            .filter(
                Order.order_status.in_([
                    "paid", "confirmed", "preparing", "ready_pickup",
                    "delivering", "delivered", "completed",
                ]),
                Order.paid_at >= day_start,
                Order.paid_at <= day_end,
            )
            .scalar() or 0
        )

        daily_details.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "order_count": day_order_count,
            "revenue": round(float(day_revenue), 2),
            "refund": round(float(day_refund), 2),
            "net": round(float(day_revenue) - float(day_refund), 2),
        })
        current_date += timedelta(days=1)

    return success_response(data={
        "period": {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
        },
        "summary": {
            "total_revenue": round(float(total_revenue), 2),
            "total_refund": round(float(total_refund), 2),
            "net_revenue": net_revenue,
        },
        "daily_details": daily_details,
    })
