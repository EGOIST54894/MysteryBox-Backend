"""外卖盲盒 - 社区系统 API 端点

提供以下接口：
- GET    /community/posts             动态流（分页，可选话题筛选）
- GET    /community/posts/{id}        帖子详情（含评论列表）
- POST   /community/posts             发布帖子（需登录）
- POST   /community/posts/{id}/like   点赞/取消点赞（需登录，toggle模式）
- POST   /community/posts/{id}/comment 发表评论（需登录）
- GET    /community/topics            话题标签列表
"""

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.services.community_service import (
    comment_post,
    create_post,
    get_post_detail,
    get_post_list,
    get_topics_list,
    like_post,
)
from app.utils.response import error_response, paginated_response, success_response

router = APIRouter()

# ──────────────────────────── Pydantic Schema ────────────────────────────


class PostCreateBody(BaseModel):
    """发布帖子请求体"""

    content: str = Field(..., min_length=1, max_length=2000, description="帖子正文内容")
    images: list[str] = Field(default_factory=list, max_length=9, description="图片URL数组，最多9张")
    topics: list[str] = Field(default_factory=list, max_length=5, description="话题标签数组，最多5个")
    location_tag: Optional[str] = Field(None, max_length=100, description="地理位置标签")
    draw_record_id: Optional[int] = Field(None, description="关联的抽卡记录ID")


class CommentCreateBody(BaseModel):
    """发表评论请求体"""

    content: str = Field(..., min_length=1, max_length=500, description="评论内容")


# ──────────────────────────── 动态流 ────────────────────────────

@router.get("/community/posts", summary="社区动态流")
def list_posts(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    topic: Optional[str] = Query(None, description="话题标签筛选"),
    db: Session = Depends(get_db),
):
    """
    获取社区动态流（公开访问）。

    按发布时间倒序排列，支持话题标签筛选和分页。
    """
    items, total = get_post_list(page=page, size=size, topic=topic, db=db)
    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 帖子详情 ────────────────────────────

@router.get("/community/posts/{post_id}", summary="帖子详情")
def post_detail(
    post_id: int,
    db: Session = Depends(get_db),
):
    """
    获取帖子详情，包含发布用户信息、关联抽卡信息和评论列表。
    """
    detail = get_post_detail(post_id=post_id, db=db)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="帖子不存在或已隐藏",
        )
    return success_response(data=detail)


# ──────────────────────────── 发布帖子 ────────────────────────────

@router.post("/community/posts", summary="发布帖子", status_code=status.HTTP_201_CREATED)
def create_new_post(
    body: PostCreateBody = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    发布一条社区动态（需登录）。

    可附带图片URL数组、话题标签、位置信息，可选关联抽卡记录。
    """
    user_id = int(current_user["sub"])

    post = create_post(
        user_id=user_id,
        content=body.content,
        images=body.images,
        topics=body.topics,
        location_tag=body.location_tag,
        draw_record_id=body.draw_record_id,
        db=db,
    )

    return success_response(
        data={
            "id": post.id,
            "user_id": post.user_id,
            "content": post.content,
            "images": post.images or [],
            "topics": post.topics or [],
            "location_tag": post.location_tag,
            "draw_record_id": post.draw_record_id,
            "likes_count": post.likes_count,
            "comments_count": post.comments_count,
            "created_at": post.created_at.isoformat() if post.created_at else None,
        },
        message="发布成功",
    )


# ──────────────────────────── 点赞/取消点赞 ────────────────────────────

@router.post("/community/posts/{post_id}/like", summary="点赞/取消点赞")
def toggle_like(
    post_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    切换点赞状态（需登录）。

    - 未点赞时: 添加点赞，返回 liked=true
    - 已点赞时: 取消点赞，返回 liked=false
    """
    user_id = int(current_user["sub"])

    try:
        is_liked = like_post(user_id=user_id, post_id=post_id, db=db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return success_response(
        data={"liked": is_liked},
        message="点赞成功" if is_liked else "已取消点赞",
    )


# ──────────────────────────── 发表评论 ────────────────────────────

@router.post("/community/posts/{post_id}/comment", summary="发表评论")
def add_comment(
    post_id: int,
    body: CommentCreateBody = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    对帖子发表评论（需登录）。
    """
    user_id = int(current_user["sub"])

    try:
        comment = comment_post(
            user_id=user_id,
            post_id=post_id,
            content=body.content,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return success_response(
        data={
            "id": comment.id,
            "user_id": comment.user_id,
            "post_id": comment.post_id,
            "content": comment.content,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        },
        message="评论成功",
    )


# ──────────────────────────── 话题列表 ────────────────────────────

@router.get("/community/topics", summary="话题列表")
def list_topics(
    db: Session = Depends(get_db),
):
    """
    获取所有话题标签列表（去重）。

    从所有正常帖子中提取并去重后返回，按名称排序。
    """
    topics = get_topics_list(db=db)
    return success_response(data=topics)
