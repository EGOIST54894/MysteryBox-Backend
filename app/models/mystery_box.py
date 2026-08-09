"""外卖盲盒 - 盲盒相关模型"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.merchant import Merchant
    from app.models.order import GroupBuyGroup, Order
    from app.models.review import Review
    from app.models.user import User


class MysteryBox(Base, TimestampMixin):
    """盲盒商品表（核心）"""

    __tablename__ = "mystery_box"

    merchant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("merchant.id", ondelete="CASCADE"), index=True, comment="商家ID"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="盲盒标题"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="盲盒描述"
    )
    cover_image: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="封面图片URL"
    )
    box_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="盲盒类型: surplus余量盲盒 group_buy拼团盲盒 surprise惊喜盲盒"
    )
    original_price: Mapped[float] = mapped_column(
        Float, nullable=False, comment="原价"
    )
    sale_price: Mapped[float] = mapped_column(
        Float, nullable=False, comment="售价"
    )
    stock: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="当前库存"
    )
    total_stock: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="总库存"
    )
    group_min_size: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="拼团最小人数"
    )
    group_max_size: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="拼团最大人数"
    )
    group_deadline: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="拼团截止时间"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, index=True, comment="状态: 0下架 1上架 2售罄 3过期"
    )
    pick_up_start: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="可取餐开始时间"
    )
    pick_up_end: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="可取餐结束时间"
    )
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="发布时间"
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="浏览次数"
    )
    sale_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="已售数量"
    )
    rating_avg: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="平均评分"
    )
    rarity: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="稀有度: ssr/sr/r/n"
    )
    meme_tags: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="梗化标签文案"
    )
    is_revealed: Mapped[bool] = mapped_column(
        default=False, comment="是否已揭晓内容"
    )

    # 关系
    merchant: Mapped["Merchant"] = relationship("Merchant", back_populates="mystery_boxes")
    tags: Mapped[List["BoxTag"]] = relationship(
        "BoxTag", back_populates="mystery_box", lazy="dynamic", cascade="all, delete-orphan"
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="mystery_box", lazy="dynamic"
    )
    group_buy_groups: Mapped[List["GroupBuyGroup"]] = relationship(
        "GroupBuyGroup", back_populates="mystery_box", lazy="dynamic"
    )
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="mystery_box", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<MysteryBox(id={self.id}, title='{self.title}')>"


class BoxTag(Base, TimestampMixin):
    """盲盒标签表"""

    __tablename__ = "box_tag"
    __table_args__ = (
        UniqueConstraint("box_id", "tag_name", name="uq_box_tag_name"),
    )

    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mystery_box.id", ondelete="CASCADE"), index=True, comment="盲盒ID"
    )
    tag_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="标签名称"
    )

    # 关系
    mystery_box: Mapped["MysteryBox"] = relationship("MysteryBox", back_populates="tags")

    def __repr__(self) -> str:
        return f"<BoxTag(id={self.id}, tag_name='{self.tag_name}')>"


class UserPreference(Base, TimestampMixin):
    """用户偏好标签表"""

    __tablename__ = "user_preference"
    __table_args__ = (
        UniqueConstraint("user_id", "tag_name", name="uq_user_preference_tag"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    tag_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="标签名称"
    )
    weight: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False, comment="偏好权重"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreference(id={self.id}, user_id={self.user_id}, tag_name='{self.tag_name}')>"
