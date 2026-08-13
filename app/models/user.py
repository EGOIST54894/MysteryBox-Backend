"""外卖盲盒 - 用户相关模型"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.review import Review


class User(Base, TimestampMixin):
    """用户表"""

    __tablename__ = "user"

    phone: Mapped[str] = mapped_column(
        String(11), unique=True, index=True, nullable=False, comment="手机号"
    )
    wechat_openid: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True, comment="微信OpenID"
    )
    nickname: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="用户昵称"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="头像URL"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希"
    )
    gender: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="性别: 0未知 1男 2女"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="状态: 1正常 0禁用"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后登录时间"
    )
    balance: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="账户余额（元）"
    )

    # 关系
    addresses: Mapped[List["UserAddress"]] = relationship(
        "UserAddress", back_populates="user", lazy="dynamic"
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="user", lazy="dynamic"
    )
    preferences: Mapped[List["UserPreference"]] = relationship(
        "UserPreference", back_populates="user", lazy="dynamic"
    )
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, phone='{self.phone}')>"


class UserAddress(Base, TimestampMixin):
    """用户收货地址表"""

    __tablename__ = "user_address"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    contact_name: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="联系人姓名"
    )
    contact_phone: Mapped[str] = mapped_column(
        String(11), nullable=False, comment="联系人电话"
    )
    province: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="省份"
    )
    city: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="城市"
    )
    district: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="区/县"
    )
    detail: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="详细地址"
    )
    latitude: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纬度"
    )
    longitude: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="经度"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否默认地址"
    )
    tag: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="地址标签（家/公司/学校等）"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="addresses")
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="address", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<UserAddress(id={self.id}, user_id={self.user_id})>"
