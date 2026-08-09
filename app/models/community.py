"""外卖盲盒 - 社区系统相关模型"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class CommunityPost(Base, TimestampMixin):
    """社区动态帖子表"""

    __tablename__ = "community_post"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="发布用户ID"
    )
    draw_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("draw_record.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联抽卡记录ID"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="帖子正文内容"
    )
    images: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="图片URL数组，JSON字符串"
    )
    topics: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="话题标签数组，JSON字符串"
    )
    location_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="地理位置标签"
    )
    likes_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="点赞数"
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="评论数"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, index=True, comment="状态: 1正常 0隐藏"
    )

    # 关系
    user: Mapped["User"] = relationship("User")
    likes: Mapped[list["PostLike"]] = relationship(
        "PostLike", back_populates="post", lazy="dynamic", cascade="all, delete-orphan"
    )
    comments: Mapped[list["PostComment"]] = relationship(
        "PostComment", back_populates="post", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CommunityPost(id={self.id}, user_id={self.user_id})>"


class PostLike(Base, TimestampMixin):
    """帖子点赞记录表"""

    __tablename__ = "post_like"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="点赞用户ID"
    )
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("community_post.id", ondelete="CASCADE"), index=True, comment="帖子ID"
    )

    # 关系
    user: Mapped["User"] = relationship("User")
    post: Mapped["CommunityPost"] = relationship("CommunityPost", back_populates="likes")

    def __repr__(self) -> str:
        return f"<PostLike(id={self.id}, user_id={self.user_id}, post_id={self.post_id})>"


class PostComment(Base, TimestampMixin):
    """帖子评论表"""

    __tablename__ = "post_comment"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="评论用户ID"
    )
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("community_post.id", ondelete="CASCADE"), index=True, comment="帖子ID"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="评论内容"
    )

    # 关系
    user: Mapped["User"] = relationship("User")
    post: Mapped["CommunityPost"] = relationship("CommunityPost", back_populates="comments")

    def __repr__(self) -> str:
        return f"<PostComment(id={self.id}, user_id={self.user_id}, post_id={self.post_id})>"
