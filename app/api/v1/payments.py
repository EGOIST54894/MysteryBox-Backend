"""
支付 API 端点

提供以下接口：
- POST /payments/create        创建支付
- POST /payments/callback      支付回调（模拟支付成功后回调）
- GET  /payments/status/{order_id}  查询支付状态
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.services.payment_service import (
    create_payment,
    get_payment_status,
    process_payment,
)
from app.utils.response import error_response, success_response

router = APIRouter()


# ──────────────────────────── 请求体模型 ────────────────────────────


class CreatePaymentRequest(BaseModel):
    """创建支付请求体"""

    order_id: int = Field(..., gt=0, description="订单ID")
    pay_method: str = Field(default="mock", description="支付方式: mock=模拟支付, alipay=支付宝, wechat_pay=微信支付")


class PaymentCallbackRequest(BaseModel):
    """支付回调请求体"""

    order_id: int = Field(..., gt=0, description="订单ID")
    token: str = Field(..., description="支付令牌（交易流水号）")


# ──────────────────────────── 创建支付 ────────────────────────────


@router.post("/create", summary="创建支付")
def create_payment_api(
    req: CreatePaymentRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    为指定订单创建支付记录，返回支付链接。

    - 需要登录
    - 仅待支付状态的订单可创建支付
    - 返回模拟支付页面的URL（pay_url字段）
    """
    try:
        user_id = int(current_user.get("sub"))

        # 校验订单归属
        from app.models.order import Order

        order = db.query(Order).filter(Order.id == req.order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该订单")

        payment_info = create_payment(
            order_id=req.order_id,
            pay_method=req.pay_method,
            db=db,
        )
        return success_response(data=payment_info, message="支付创建成功")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 支付回调（模拟） ────────────────────────────


@router.post("/callback", summary="支付回调（模拟支付成功）")
def payment_callback_api(
    req: PaymentCallbackRequest,
    db: Session = Depends(get_db),
):
    """
    模拟支付成功后的回调接口。

    由模拟支付页面在用户确认支付后调用。
    不需要登录态（实际第三方支付回调也不会带用户Token）。
    通过订单ID和支付令牌（transaction_no）进行校验。

    处理流程：
    1. 校验支付令牌
    2. 更新支付记录状态为 success
    3. 更新订单状态为 paid
    """
    try:
        from app.models.payment import PaymentRecord

        # 校验支付令牌
        payment = (
            db.query(PaymentRecord)
            .filter(
                PaymentRecord.order_id == req.order_id,
                PaymentRecord.transaction_no == req.token,
                PaymentRecord.status == "pending",
            )
            .first()
        )
        if not payment:
            raise ValueError("支付令牌无效或支付已处理")

        # 处理支付
        payment = process_payment(order_id=req.order_id, db=db)

        payment_data = {
            "payment_id": payment.id,
            "order_id": req.order_id,
            "transaction_no": payment.transaction_no,
            "status": payment.status,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        }
        return success_response(data=payment_data, message="支付成功")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ──────────────────────────── 查询支付状态 ────────────────────────────


@router.get("/status/{order_id}", summary="查询支付状态")
def get_payment_status_api(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    查询指定订单的支付状态。

    - 需要登录
    - 返回支付记录详情和订单支付状态
    """
    try:
        user_id = int(current_user.get("sub"))

        # 校验订单归属
        from app.models.order import Order

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
        if order.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该订单")

        status_data = get_payment_status(order_id=order_id, db=db)
        return success_response(data=status_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
