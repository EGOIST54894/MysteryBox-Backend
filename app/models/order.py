"""外卖盲盒 - 订单相关模型"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.delivery import DeliveryPersonnel
    from app.models.mystery_box import MysteryBox
    from app.models.payment import PaymentRecord
    from app.models.review import Review
    from app.models.user import User, UserAddress


class Order(Base, TimestampMixin):
    """订单表（核心，包含完整订单状态机）"""

    __tablename__ = "`order`"

    order_no: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False, comment="订单编号"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mystery_box.id", ondelete="RESTRICT"), index=True, comment="盲盒ID"
    )
    address_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_address.id", ondelete="SET NULL"), index=True, nullable=True, comment="地址ID"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="购买数量"
    )
    unit_price: Mapped[float] = mapped_column(
        Float, nullable=False, comment="单价"
    )
    total_amount: Mapped[float] = mapped_column(
        Float, nullable=False, comment="总金额"
    )
    discount_amount: Mapped[float] = mapped_column(
        Float, default=0.00, nullable=False, comment="优惠金额"
    )
    paid_amount: Mapped[float] = mapped_column(
        Float, default=0.00, nullable=False, comment="实付金额"
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("group_buy_group.id", ondelete="SET NULL"), index=True, nullable=True, comment="拼团ID"
    )
    group_role: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="拼团角色: leader团长 member团员"
    )
    order_status: Mapped[str] = mapped_column(
        String(20), default="pending_pay", nullable=False, index=True,
        comment="订单状态: pending_pay待支付 paid已支付 confirmed已确认 "
                "preparing准备中 ready_pickup待取餐 delivering配送中 "
                "delivered已送达 completed已完成 cancelled已取消 "
                "refunding退款中 refunded已退款"
    )
    cancel_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="取消原因"
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="支付时间"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="确认时间"
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="送达时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="完成时间"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="取消时间"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="orders")
    mystery_box: Mapped["MysteryBox"] = relationship("MysteryBox", back_populates="orders")
    address: Mapped["UserAddress | None"] = relationship("UserAddress", back_populates="orders")
    group_buy_group: Mapped["GroupBuyGroup | None"] = relationship(
        "GroupBuyGroup", back_populates="orders"
    )
    payments: Mapped[List["PaymentRecord"]] = relationship(
        "PaymentRecord", back_populates="order", lazy="dynamic"
    )
    delivery_order: Mapped["DeliveryOrder | None"] = relationship(
        "DeliveryOrder", back_populates="order", uselist=False
    )
    review: Mapped["Review | None"] = relationship(
        "Review", back_populates="order", uselist=False
    )

    @property
    def is_paid(self) -> bool:
        """是否已支付"""
        return self.order_status not in ("pending_pay", "cancelled", "refunding", "refunded")

    @property
    def can_cancel(self) -> bool:
        """是否可以取消"""
        return self.order_status in ("pending_pay", "paid")

    @property
    def can_refund(self) -> bool:
        """是否可以退款"""
        return self.order_status in ("paid", "confirmed", "preparing")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, order_no='{self.order_no}')>"


class GroupBuyGroup(Base, TimestampMixin):
    """拼团群组表"""

    __tablename__ = "group_buy_group"

    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mystery_box.id", ondelete="CASCADE"), index=True, comment="盲盒ID"
    )
    leader_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), comment="团长用户ID"
    )
    current_size: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="当前拼团人数"
    )
    target_size: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="目标拼团人数"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="gathering", nullable=False, index=True,
        comment="拼团状态: gathering进行中 completed已完成 expired已过期 cancelled已取消"
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="拼团截止时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="拼团完成时间"
    )

    # 关系
    mystery_box: Mapped["MysteryBox"] = relationship("MysteryBox", back_populates="group_buy_groups")
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="group_buy_group", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<GroupBuyGroup(id={self.id}, box_id={self.box_id}, status='{self.status}')>"


class DeliveryOrder(Base, TimestampMixin):
    """配送订单表"""

    __tablename__ = "delivery_order"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("`order`.id", ondelete="CASCADE"), unique=True, index=True, comment="订单ID"
    )
    delivery_person_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("delivery_personnel.id", ondelete="SET NULL"), index=True, nullable=True, comment="配送员ID"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="assigned", nullable=False, index=True,
        comment="配送状态: assigned已分配 picked_up已取货 delivering配送中 delivered已送达"
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="分配时间"
    )
    picked_up_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="取货时间"
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="送达时间"
    )

    # 关系
    order: Mapped["Order"] = relationship("Order", back_populates="delivery_order")
    delivery_person: Mapped["DeliveryPersonnel | None"] = relationship(
        "DeliveryPersonnel", back_populates="delivery_orders"
    )

    def __repr__(self) -> str:
        return f"<DeliveryOrder(id={self.id}, order_id={self.order_id}, status='{self.status}')>"
