"""外卖盲盒 - 支付相关模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class PaymentRecord(Base, TimestampMixin):
    """支付记录表"""

    __tablename__ = "payment_record"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("`order`.id", ondelete="CASCADE"), index=True, comment="订单ID"
    )
    transaction_no: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="第三方交易流水号"
    )
    pay_method: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="支付方式: alipay支付宝 wechat_pay微信支付 mock模拟支付"
    )
    pay_amount: Mapped[float] = mapped_column(
        Float, nullable=False, comment="支付金额"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
        comment="支付状态: pending待支付 success成功 failed失败 refunded已退款"
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="支付时间"
    )
    raw_response: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="第三方支付原始响应(JSON对象)"
    )

    # 关系
    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    def __repr__(self) -> str:
        return f"<PaymentRecord(id={self.id}, transaction_no='{self.transaction_no}')>"
