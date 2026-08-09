"""外卖盲盒 - 抽卡系统相关模型"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.mystery_box import MysteryBox
    from app.models.user import User


class DrawRecord(Base, TimestampMixin):
    """抽卡记录表 —— 记录用户每次抽卡行为"""

    __tablename__ = "draw_record"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mystery_box.id", ondelete="CASCADE"), index=True, comment="盲盒ID"
    )
    rarity: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="抽中稀有度: ssr/sr/r/n"
    )
    draw_price: Mapped[float] = mapped_column(
        Float, nullable=False, comment="抽卡支付金额"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", comment="状态: pending(未下单) / ordered(已下单)"
    )
    draw_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="用户当日抽卡次数序号"
    )

    # 关系
    user: Mapped["User"] = relationship("User")
    mystery_box: Mapped["MysteryBox"] = relationship("MysteryBox")

    def __repr__(self) -> str:
        return f"<DrawRecord(id={self.id}, user_id={self.user_id}, rarity='{self.rarity}')>"
