"""外卖盲盒 - 社区系统业务逻辑层

提供社区动态发布、列表查询、点赞/取消点赞、评论等功能。
"""

from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.community import CommunityPost, PostComment, PostLike
from app.models.draw import DrawRecord
from app.models.mystery_box import MysteryBox
from app.models.user import User


def create_post(
    user_id: int,
    content: str,
    images: Optional[list] = None,
    topics: Optional[list] = None,
    location_tag: Optional[str] = None,
    draw_record_id: Optional[int] = None,
    db: Session = None,
) -> CommunityPost:
    """
    创建社区动态帖子。

    Args:
        user_id: 发布用户ID
        content: 帖子正文内容
        images: 图片URL数组
        topics: 话题标签数组
        location_tag: 地理位置标签
        draw_record_id: 关联的抽卡记录ID（可选）
        db: 数据库会话

    Returns:
        新创建的 CommunityPost 对象
    """
    post = CommunityPost(
        user_id=user_id,
        draw_record_id=draw_record_id,
        content=content,
        images=images or [],
        topics=topics or [],
        location_tag=location_tag,
        likes_count=0,
        comments_count=0,
        status=1,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def get_post_list(
    page: int = 1,
    size: int = 10,
    topic: Optional[str] = None,
    db: Session = None,
) -> tuple:
    """
    获取社区动态流（分页，可选话题筛选）。

    Args:
        page: 页码（从1开始）
        size: 每页条数
        topic: 话题标签筛选（可选）
        db: 数据库会话

    Returns:
        (items: list[dict], total: int)
    """
    # 仅查询状态正常的帖子
    q = db.query(CommunityPost).filter(CommunityPost.status == 1)

    # 话题筛选：MySQL JSON 字段模糊匹配
    if topic:
        q = q.filter(CommunityPost.topics.contains(topic))

    total = q.count()

    posts = (
        q.order_by(desc(CommunityPost.created_at))
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for post in posts:
        user = db.query(User).filter(User.id == post.user_id).first()
        items.append(_format_post_item(post, user, db))

    return items, total


def get_post_detail(post_id: int, db: Session) -> Optional[dict]:
    """
    获取帖子详情，包含用户信息和评论列表。

    Args:
        post_id: 帖子ID
        db: 数据库会话

    Returns:
        帖子详情字典，不存在时返回 None
    """
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post or post.status != 1:
        return None

    user = db.query(User).filter(User.id == post.user_id).first()

    result = _format_post_item(post, user, db)

    # 加载评论列表
    comments = (
        db.query(PostComment)
        .filter(PostComment.post_id == post.id)
        .order_by(PostComment.created_at)
        .all()
    )

    comment_list = []
    for comment in comments:
        comment_user = db.query(User).filter(User.id == comment.user_id).first()
        comment_list.append({
            "id": comment.id,
            "user_id": comment.user_id,
            "user_nickname": comment_user.nickname or f"用户{comment.user_id}" if comment_user else f"用户{comment.user_id}",
            "user_avatar": comment_user.avatar_url if comment_user else None,
            "content": comment.content,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        })

    result["comments"] = comment_list
    return result


def like_post(user_id: int, post_id: int, db: Session) -> bool:
    """
    点赞/取消点赞（toggle 模式）。

    如果用户已点赞则取消，未点赞则添加。
    同时更新帖子的 likes_count 字段。

    Args:
        user_id: 用户ID
        post_id: 帖子ID
        db: 数据库会话

    Returns:
        True 表示已点赞，False 表示已取消点赞

    Raises:
        ValueError: 帖子不存在
    """
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post or post.status != 1:
        raise ValueError("帖子不存在或已隐藏")

    # 查找已有点赞记录
    existing = (
        db.query(PostLike)
        .filter(PostLike.user_id == user_id, PostLike.post_id == post_id)
        .first()
    )

    if existing:
        # 取消点赞
        db.delete(existing)
        post.likes_count = max(0, post.likes_count - 1)
        db.commit()
        return False
    else:
        # 添加点赞
        new_like = PostLike(user_id=user_id, post_id=post_id)
        db.add(new_like)
        post.likes_count = post.likes_count + 1
        db.commit()
        return True


def comment_post(user_id: int, post_id: int, content: str, db: Session) -> PostComment:
    """
    发表评论。

    Args:
        user_id: 评论用户ID
        post_id: 帖子ID
        content: 评论内容
        db: 数据库会话

    Returns:
        新创建的 PostComment 对象

    Raises:
        ValueError: 帖子不存在或内容为空
    """
    if not content or not content.strip():
        raise ValueError("评论内容不能为空")

    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post or post.status != 1:
        raise ValueError("帖子不存在或已隐藏")

    comment = PostComment(
        user_id=user_id,
        post_id=post_id,
        content=content.strip(),
    )
    db.add(comment)
    post.comments_count = post.comments_count + 1
    db.commit()
    db.refresh(comment)
    return comment


def get_topics_list(db: Session) -> list:
    """
    获取所有话题标签列表（去重）。

    从所有正常帖子中提取 topics JSON 字段中的话题，去重后返回。

    Args:
        db: 数据库会话

    Returns:
        话题名称字符串列表
    """
    posts = (
        db.query(CommunityPost.topics)
        .filter(CommunityPost.status == 1, CommunityPost.topics.isnot(None))
        .all()
    )

    topics_set = set()
    for (topics_data,) in posts:
        if topics_data and isinstance(topics_data, list):
            for t in topics_data:
                if t and isinstance(t, str):
                    topics_set.add(t.strip())

    # 按名称排序
    return sorted(list(topics_set))


# ──────────────────────────── 内部辅助函数 ────────────────────────────

def _format_post_item(post: CommunityPost, user: Optional[User], db: Session) -> dict:
    """格式化帖子为字典响应"""
    # 获取关联的抽卡信息
    draw_info = None
    if post.draw_record_id:
        draw_record = db.query(DrawRecord).filter(DrawRecord.id == post.draw_record_id).first()
        if draw_record:
            box = db.query(MysteryBox).filter(MysteryBox.id == draw_record.box_id).first()
            draw_info = {
                "rarity": draw_record.rarity,
                "box_title": box.title if box else None,
                "box_type": box.box_type if box else None,
                "cover_image": box.cover_image if box else None,
            }

    return {
        "id": post.id,
        "user_id": post.user_id,
        "user_nickname": user.nickname or f"用户{post.user_id}" if user else f"用户{post.user_id}",
        "user_avatar": user.avatar_url if user else None,
        "draw_record_id": post.draw_record_id,
        "draw_info": draw_info,
        "content": post.content,
        "images": post.images or [],
        "topics": post.topics or [],
        "location_tag": post.location_tag,
        "likes_count": post.likes_count,
        "comments_count": post.comments_count,
        "status": post.status,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }
