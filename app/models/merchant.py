"""外卖盲盒 - 商家相关模型"""

from typing import TYPE_CHECKING, List

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.mystery_box import MysteryBox


class Merchant(Base, TimestampMixin):
    """商家表"""

    __tablename__ = "merchant"

    phone: Mapped[str] = mapped_column(
        String(11), unique=True, index=True, nullable=False, comment="手机号"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希"
    )
    nickname: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="商家昵称"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="头像URL"
    )
    store_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="店铺名称"
    )
    logo_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="店铺Logo URL"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="店铺描述"
    )
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="经营品类"
    )
    business_license: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="营业执照图片URL"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True, comment="状态: 0待审核 1通过 2拒绝 3禁用"
    )
    latitude: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纬度"
    )
    longitude: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="经度"
    )
    province: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="所在省份"
    )
    city: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="所在城市"
    )
    district: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="所在区/县"
    )
    address_detail: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="详细地址"
    )
    business_hours: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="营业时间(JSON字符串)"
    )
    rating_avg: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="平均评分"
    )
    balance: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="账户余额（元），订单完成后按 70% 分成入账"
    )

    # 关系
    mystery_boxes: Mapped[List["MysteryBox"]] = relationship(
        "MysteryBox", back_populates="merchant", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Merchant(id={self.id}, store_name='{self.store_name}')>"
