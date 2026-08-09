"""
模拟支付业务逻辑模块

提供支付创建、支付处理、退款等核心功能。
使用模拟支付方式（mock），不需要对接真实第三方支付平台。

流程：
    1. 用户发起支付请求 -> create_payment() 生成交易流水号和支付链接
    2. 用户"支付"成功 -> process_payment() 更新支付记录和订单状态
    3. 退款 -> refund_payment() 处理退款
"""

import random
import string
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.payment import PaymentRecord
from app.services.order_service import update_order_status


def _generate_transaction_no() -> str:
    """生成交易流水号：TXN + 时间戳 + 4位随机数字"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = "".join(random.choices(string.digits, k=4))
    return f"TXN{timestamp}{random_part}"


# ──────────────────────────── 创建支付 ────────────────────────────


def create_payment(
    order_id: int,
    pay_method: str = "mock",
    db: Session = None,
) -> dict:
    """
    创建支付记录，生成交易流水号和模拟支付链接。

    Args:
        order_id: 订单主键ID
        pay_method: 支付方式，默认 "mock"（模拟支付）
        db: 数据库会话

    Returns:
        支付信息字典，包含:
        - transaction_no: 交易流水号
        - pay_amount: 支付金额
        - pay_url: 模拟支付页面的URL
        - status: 支付状态 (pending)

    Raises:
        ValueError: 订单不存在、订单状态不允许支付
    """
    # 查询订单
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    # 只有 pending_pay 状态的订单才能发起支付
    if order.order_status != "pending_pay":
        raise ValueError(f"订单状态 '{order.order_status}' 不允许发起支付，仅待支付订单可支付")

    # 检查是否已有进行中的支付记录，避免重复创建
    existing_payment = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.order_id == order_id,
            PaymentRecord.status == "pending",
        )
        .first()
    )
    if existing_payment:
        # 返回已有的支付信息
        return {
            "payment_id": existing_payment.id,
            "order_id": order_id,
            "transaction_no": existing_payment.transaction_no,
            "pay_amount": float(existing_payment.pay_amount),
            "pay_method": existing_payment.pay_method,
            "status": existing_payment.status,
            "pay_url": f"/api/v1/mock-pay?order_id={order_id}&token={existing_payment.transaction_no}",
        }

    # 生成交易流水号
    transaction_no = _generate_transaction_no()
    pay_amount = float(order.paid_amount)

    # 创建支付记录
    payment = PaymentRecord(
        order_id=order_id,
        transaction_no=transaction_no,
        pay_method=pay_method,
        pay_amount=pay_amount,
        status="pending",
        raw_response={
            "mock": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "payment_id": payment.id,
        "order_id": order_id,
        "transaction_no": transaction_no,
        "pay_amount": pay_amount,
        "pay_method": pay_method,
        "status": "pending",
        "pay_url": f"/api/v1/mock-pay?order_id={order_id}&token={transaction_no}",
    }


# ──────────────────────────── 处理支付（模拟支付成功） ────────────────────────────


def process_payment(order_id: int, db: Session) -> PaymentRecord:
    """
    处理支付成功回调（模拟支付成功后调用）。
    1. 更新 PaymentRecord 状态为 success
    2. 更新订单状态为 paid
    3. 记录支付时间

    Args:
        order_id: 订单主键ID
        db: 数据库会话

    Returns:
        更新后的 PaymentRecord 实例

    Raises:
        ValueError: 找不到待处理的支付记录、订单状态异常
    """
    # 查找该订单的 pending 状态支付记录
    payment = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.order_id == order_id,
            PaymentRecord.status == "pending",
        )
        .first()
    )
    if not payment:
        raise ValueError("未找到待处理的支付记录，请先创建支付")

    # 校验订单状态
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    if order.order_status != "pending_pay":
        # 如果订单已经不是待支付状态，则标记支付为失败
        payment.status = "failed"
        payment.raw_response = payment.raw_response or {}
        payment.raw_response["error"] = f"订单状态异常: {order.order_status}"
        db.commit()
        db.refresh(payment)
        raise ValueError(f"订单状态异常，当前状态: {order.order_status}，无法完成支付")

    now = datetime.now(timezone.utc)

    # 更新支付记录
    payment.status = "success"
    payment.paid_at = now
    payment.raw_response = payment.raw_response or {}
    payment.raw_response["completed_at"] = now.isoformat()
    payment.raw_response["mock_success"] = True

    # 更新订单状态
    order.order_status = "paid"
    order.paid_at = now

    # 更新支付记录的实付金额（与订单一致）
    payment.pay_amount = float(order.paid_amount)

    db.commit()
    db.refresh(payment)
    return payment


# ──────────────────────────── 退款处理 ────────────────────────────


def refund_payment(order_id: int, db: Session) -> PaymentRecord:
    """
    处理退款（模拟）。
    1. 更新 PaymentRecord 状态为 refunded
    2. 更新订单状态为 refunded
    3. 恢复盲盒库存

    Args:
        order_id: 订单主键ID
        db: 数据库会话

    Returns:
        更新后的 PaymentRecord 实例

    Raises:
        ValueError: 找不到成功的支付记录
    """
    # 查找成功的支付记录
    payment = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.order_id == order_id,
            PaymentRecord.status == "success",
        )
        .first()
    )
    if not payment:
        raise ValueError("未找到已完成的支付记录，无法退款")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    # 校验订单状态（应该是 refunding）
    if order.order_status != "refunding":
        raise ValueError(f"订单状态 '{order.order_status}' 不允许退款，需先进入 refunding 状态")

    now = datetime.now(timezone.utc)

    # 更新支付记录
    payment.status = "refunded"
    payment.raw_response = payment.raw_response or {}
    payment.raw_response["refunded_at"] = now.isoformat()
    payment.raw_response["mock_refund"] = True

    # 更新订单状态
    order.order_status = "refunded"

    # 恢复库存
    from app.models.mystery_box import MysteryBox

    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if box:
        box.stock += order.quantity
        box.sale_count = max(0, box.sale_count - order.quantity)
        if box.status == 2 and box.stock > 0:
            box.status = 1

    db.commit()
    db.refresh(payment)
    return payment


# ──────────────────────────── 查询支付状态 ────────────────────────────


def get_payment_status(order_id: int, db: Session) -> dict:
    """
    查询订单的支付状态。

    Args:
        order_id: 订单主键ID
        db: 数据库会话

    Returns:
        支付状态信息字典
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    # 获取最新的支付记录
    payment = (
        db.query(PaymentRecord)
        .filter(PaymentRecord.order_id == order_id)
        .order_by(PaymentRecord.created_at.desc())
        .first()
    )

    result = {
        "order_id": order_id,
        "order_no": order.order_no,
        "order_status": order.order_status,
        "total_amount": float(order.total_amount),
        "paid_amount": float(order.paid_amount),
        "is_paid": order.order_status not in ("pending_pay",),
    }

    if payment:
        result["payment"] = {
            "id": payment.id,
            "transaction_no": payment.transaction_no,
            "pay_method": payment.pay_method,
            "pay_amount": float(payment.pay_amount),
            "status": payment.status,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        }
    else:
        result["payment"] = None

    return result
