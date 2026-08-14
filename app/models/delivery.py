"""外卖盲盒 - 配送人员模型"""

from typing import TYPE_CHECKING, List

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import DeliveryOrder


class DeliveryPersonnel(Base, TimestampMixin):
    """配送人员表"""

    __tablename__ = "delivery_personnel"

    phone: Mapped[str] = mapped_column(
        String(11), unique=True, index=True, nullable=False, comment="手机号"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希"
    )
    real_name: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="真实姓名"
    )
    nickname: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="配送员昵称"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="头像URL"
    )
    id_card: Mapped[str] = mapped_column(
        String(18), nullable=False, comment="身份证号"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True, comment="状态: 0待审核 1在线 2离线 3禁用"
    )
    current_lat: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="当前纬度"
    )
    current_lng: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="当前经度"
    )
    rating_avg: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="平均评分"
    )
    completed_orders: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="已完成订单数"
    )
    balance: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, comment="账户余额（元），订单完成后按 30% 分成入账"
    )

    # 关系
    delivery_orders: Mapped[List["DeliveryOrder"]] = relationship(
        "DeliveryOrder", back_populates="delivery_person", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<DeliveryPersonnel(id={self.id}, real_name='{self.real_name}')>"
