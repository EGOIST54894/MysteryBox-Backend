"""外卖盲盒 - 评价相关模型"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.mystery_box import MysteryBox
    from app.models.order import Order
    from app.models.user import User


class Review(Base, TimestampMixin):
    """评价表"""

    __tablename__ = "review"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("`order`.id", ondelete="CASCADE"), unique=True, index=True, comment="订单ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mystery_box.id", ondelete="CASCADE"), index=True, comment="盲盒ID"
    )
    rating: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="评分: 1-5"
    )
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="评价内容"
    )
    images: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="评价图片URL列表"
    )
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否匿名"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="状态: 1正常 0隐藏"
    )

    # 关系
    order: Mapped["Order"] = relationship("Order", back_populates="review")
    user: Mapped["User"] = relationship("User", back_populates="reviews")
    mystery_box: Mapped["MysteryBox"] = relationship("MysteryBox", back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review(id={self.id}, order_id={self.order_id}, rating={self.rating})>"
