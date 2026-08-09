"""
订单 API 端点

提供以下接口：
- POST   /orders                  创建订单（需登录）
- GET    /orders                  我的订单列表（支持状态筛选 + 分页）
- GET    /orders/{id}             订单详情
- POST   /orders/{id}/cancel      取消订单
- POST   /orders/{id}/confirm-receipt  确认收货
- POST   /orders/{id}/pay         发起支付
- GET    /orders/{id}/tracking    获取配送追踪信息
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.schemas.order import OrderCreate
from app.services.order_service import (
    cancel_order,
    confirm_receipt,
    create_order,
    get_order_detail,
    get_order_tracking,
    get_user_orders,
)
from app.services.payment_service import create_payment
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()


# ═══════════════════ 简单格式（必须在 /{order_id} 之前）═══════════════

@router.get("/simple", summary="订单列表（平铺格式）")
def orders_simple(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """返回扁平化订单数组，方便ArkTS解析"""
    user_id = int(current_user.get("sub"))
    orders, _ = get_user_orders(user_id=user_id, status_filter=None, page=1, size=100, db=db)
    result = []
    for o in orders:
        oid = o.get("id", 0) if isinstance(o, dict) else getattr(o, "id", 0)
        ono = o.get("order_no", "") if isinstance(o, dict) else getattr(o, "order_no", "")
        bid = o.get("box_id", 0) if isinstance(o, dict) else getattr(o, "box_id", 0)
        ost = o.get("order_status", "") if isinstance(o, dict) else getattr(o, "order_status", "")
        paid = o.get("paid_amount", 0) if isinstance(o, dict) else getattr(o, "paid_amount", 0)
        total = o.get("total_amount", 0) if isinstance(o, dict) else getattr(o, "total_amount", 0)
        qty = o.get("quantity", 1) if isinstance(o, dict) else getattr(o, "quantity", 1)
        cat = o.get("created_at", "") if isinstance(o, dict) else getattr(o, "created_at", "")
        result.append({
            "id": oid,
            "orderNo": ono or "",
            "boxId": bid or 0,
            "boxTitle": "盲盒商品",
            "boxCover": "",
            "boxType": "surplus",
            "merchantName": "",
            "status": "paid" if ost == "pending_pay" else (ost or ""),
            "actualPrice": int(float(paid or total or 0) * 100),
            "quantity": qty or 1,
            "createdAt": str(cat or ""),
            "updatedAt": str(cat or ""),
        })
    return {"code": 200, "message": "success", "data": result}


# ──────────────────────────── 创建订单 ────────────────────────────


@router.post("", summary="创建订单")
def create_order_api(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    创建新订单。

    - 需要登录（用户角色）
    - 自动扣减盲盒库存
    - 拼团类型盲盒自动创建或加入拼团组
    - 订单初始状态为 pending_pay（待支付）
    - 30分钟内未支付系统将自动取消（通过后台任务实现）
    """
    try:
        user_id = int(current_user.get("sub"))
        order = create_order(user_id=user_id, data=data, db=db)

        # 构造返回数据
        order_data = {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "box_id": order.box_id,
            "address_id": order.address_id,
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "discount_amount": float(order.discount_amount),
            "paid_amount": float(order.paid_amount),
            "group_id": order.group_id,
            "group_role": order.group_role,
            "order_status": order.order_status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        return success_response(data=order_data, message="订单创建成功，请尽快完成支付")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 我的订单列表 ────────────────────────────


@router.get("", summary="我的订单列表")
def list_my_orders(
    status_filter: str = Query(None, alias="status", description="按订单状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前用户的订单列表。

    - 支持按订单状态筛选（如 pending_pay, paid, completed 等）
    - 支持分页
    - 按创建时间倒序排列
    """
    user_id = int(current_user.get("sub"))
    items, total = get_user_orders(
        user_id=user_id,
        status_filter=status_filter,
        page=page,
        size=size,
        db=db,
    )
    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 订单详情 ────────────────────────────


@router.get("/{order_id}", summary="订单详情")
def get_order_detail_api(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取指定订单的详细信息。

    包含：
    - 订单基本信息
    - 关联盲盒信息
    - 收货地址信息
    - 配送状态（如有）
    - 拼团信息（如有）
    """
    try:
        user_id = int(current_user.get("sub"))
        order_data = get_order_detail(order_id=order_id, user_id=user_id, db=db)
        return success_response(data=order_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 取消订单 ────────────────────────────


class CancelOrderBody(BaseModel):
    """取消订单请求体"""
    reason: str | None = Field(None, description="取消原因")


@router.post("/{order_id}/cancel", summary="取消订单")
def cancel_order_api(
    order_id: int,
    reason: str | None = Query(None, description="取消原因"),
    body: CancelOrderBody | None = Body(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    取消订单。

    - pending_pay 状态：直接取消，自动恢复盲盒库存
    - paid 状态：进入 refunding 退款流程，需支付服务处理后完成退款
    - 其他状态不允许取消
    - reason 可通过 query 参数或请求体传递
    """
    try:
        user_id = int(current_user.get("sub"))
        # 优先使用 body 中的 reason，其次使用 query 参数
        cancel_reason = (body.reason if body and body.reason else reason)
        order = cancel_order(order_id=order_id, user_id=user_id, reason=cancel_reason, db=db)

        # 如果进入了退款状态，自动触发退款
        if order.order_status == "refunding":
            from app.services.payment_service import refund_payment

            refund_payment(order_id=order.id, db=db)
            db.refresh(order)

        order_data = {
            "id": order.id,
            "order_no": order.order_no,
            "order_status": order.order_status,
            "cancel_reason": order.cancel_reason,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        }
        return success_response(data=order_data, message="订单已取消")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 确认收货 ────────────────────────────


@router.post("/{order_id}/confirm-receipt", summary="确认收货")
def confirm_receipt_api(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    确认收货，将订单状态从 delivered 变为 completed。

    - 只能确认已送达（delivered）状态的订单
    - 确认后订单进入 completed 终态
    """
    try:
        user_id = int(current_user.get("sub"))
        order = confirm_receipt(order_id=order_id, user_id=user_id, db=db)
        order_data = {
            "id": order.id,
            "order_no": order.order_no,
            "order_status": order.order_status,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        }
        return success_response(data=order_data, message="已确认收货")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 发起支付 ────────────────────────────


@router.post("/{order_id}/pay", summary="发起支付")
def pay_order_api(
    order_id: int,
    pay_method: str = Query("mock", description="支付方式: mock=模拟支付"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    为订单创建支付记录并返回支付链接。

    - 仅 pending_pay 状态的订单可发起支付
    - 返回的 pay_url 为模拟支付页面地址
    - 支付有效期30分钟
    """
    try:
        user_id = int(current_user.get("sub"))
        # 校验订单归属
        from app.models.order import Order

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该订单")

        payment_info = create_payment(order_id=order_id, pay_method=pay_method, db=db)
        return success_response(data=payment_info, message="支付已创建，请完成支付")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 配送追踪 ────────────────────────────


@router.get("/{order_id}/tracking", summary="获取配送追踪信息")
def get_order_tracking_api(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取订单的配送追踪信息。

    包含配送状态、配送员信息（如已分配）、各时间节点等。
    """
    try:
        user_id = int(current_user.get("sub"))
        tracking_data = get_order_tracking(order_id=order_id, user_id=user_id, db=db)
        return success_response(data=tracking_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
