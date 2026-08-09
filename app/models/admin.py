"""外卖盲盒 - 管理员模型"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Admin(Base, TimestampMixin):
    """管理员表"""

    __tablename__ = "admin"

    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False, comment="用户名"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希"
    )
    role: Mapped[str] = mapped_column(
        String(20), default="admin", nullable=False, comment="角色: admin普通管理员 super_admin超级管理员"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="状态: 1正常 0禁用"
    )

    def __repr__(self) -> str:
        return f"<Admin(id={self.id}, username='{self.username}', role='{self.role}')>"
