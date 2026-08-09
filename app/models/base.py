"""
SQLAlchemy 模型基类
定义所有数据表共有的字段（id, created_at, updated_at）以及数据库引擎和会话工厂。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, func
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings


# ==================== ORM 基类 ====================
class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative 基类。
    所有模型类都应继承此类，以获得统一的表结构惯例。
    """

    __abstract__ = True


# ==================== 混入类：通用表字段 ====================
class TimestampMixin:
    """
    时间戳混入类。
    为模型添加 id、created_at、updated_at 三个通用字段。

    使用方式:
        class User(TimestampMixin, Base):
            __tablename__ = "users"
            username: Mapped[str] = mapped_column(String(50))
    """

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )


# ==================== 数据库引擎 ====================
_is_sqlite = "sqlite" in settings.DATABASE_URL

_engine_kwargs = {
    "echo": settings.DEBUG,
}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_pre_ping"] = True

engine = _create_engine(settings.DATABASE_URL, **_engine_kwargs)

# ==================== 会话工厂 ====================
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # 提交后不使对象过期，避免懒加载报错
)


# ==================== 获取数据库会话的便捷函数 ====================
def get_db_session() -> Session:
    """
    返回一个新的数据库会话实例。
    注意：调用方需要自行关闭会话。
    """
    return SessionLocal()
