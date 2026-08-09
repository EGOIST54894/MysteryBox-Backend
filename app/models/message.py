"""外卖盲盒 - 消息系统模型"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.delivery import DeliveryPersonnel
    from app.models.merchant import Merchant
    from app.models.order import Order
    from app.models.user import User


class Message(Base, TimestampMixin):
    """消息表 — 支持三端（用户/商家/配送员）互通消息"""

    __tablename__ = "message"

    sender_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="发送者ID"
    )
    sender_role: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="发送者角色: user/merchant/delivery"
    )
    receiver_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="接收者ID"
    )
    receiver_role: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="接收者角色: user/merchant/delivery"
    )
    order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("`order`.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联订单ID"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    message_type: Mapped[str] = mapped_column(
        String(20), default="text", nullable=False, comment="消息类型: text/system"
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="是否已读"
    )
    read_at: Mapped[str | None] = mapped_column(
        DateTime, nullable=True, comment="阅读时间"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, sender={self.sender_role}:{self.sender_id}, receiver={self.receiver_role}:{self.receiver_id})>"
