"""
消息系统 API 端点

支持用户/商家/配送员三端消息互通：
- GET    /messages/conversations  会话列表
- GET    /messages/{target_role}/{target_id}  消息历史
- POST   /messages                发送消息
- PUT    /messages/{id}/read      标记已读
- GET    /messages/unread-count   未读消息数
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.delivery import DeliveryPersonnel
from app.models.merchant import Merchant
from app.models.message import Message
from app.models.user import User
from app.utils.response import paginated_response, success_response

router = APIRouter()


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    receiver_id: int = Field(..., description="接收者ID")
    receiver_role: str = Field(..., pattern="^(user|merchant|delivery)$", description="接收者角色")
    content: str = Field(..., min_length=1, max_length=2000, description="消息内容")
    order_id: int | None = Field(None, description="关联订单ID")


def get_current_user_from_token(db: Session = Depends(get_db)):
    """从请求上下文中获取当前用户信息（简化版依赖注入，auth.py 中使用 get_current_user）"""
    # 这个函数在实际请求中不会直接被调用，而是由各个端点自行处理认证
    pass


def _get_entity_info(entity_id: int, role: str, db: Session) -> dict:
    """根据角色和ID获取实体信息"""
    if role == "user":
        u = db.query(User).filter(User.id == entity_id).first()
        if u:
            return {"id": u.id, "name": u.nickname or f"用户{u.phone[-4:]}", "avatar": u.avatar_url or "", "phone": u.phone}
    elif role == "merchant":
        m = db.query(Merchant).filter(Merchant.id == entity_id).first()
        if m:
            return {"id": m.id, "name": m.nickname or m.store_name, "avatar": m.avatar_url or m.logo_url or "", "phone": m.phone}
    elif role == "delivery":
        d = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.id == entity_id).first()
        if d:
            return {"id": d.id, "name": d.nickname or d.real_name, "avatar": d.avatar_url or "", "phone": d.phone}
    return {"id": entity_id, "name": f"用户{entity_id}", "avatar": "", "phone": ""}


# ──────────────────────────── 会话列表 ────────────────────────────


@router.get("/conversations", summary="会话列表")
def list_conversations(
    user_id: int = Query(..., description="当前用户ID"),
    role: str = Query(..., pattern="^(user|merchant|delivery)$", description="当前角色"),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的会话列表（按对方分组，显示最后一条消息预览和未读数）。
    请求示例：GET /messages/conversations?user_id=1&role=user
    """
    # 查询所有与当前用户相关的消息
    sent = db.query(Message).filter(
        Message.sender_id == user_id,
        Message.sender_role == role,
    ).all()
    received = db.query(Message).filter(
        Message.receiver_id == user_id,
        Message.receiver_role == role,
    ).all()

    # 按 (对方ID, 对方角色) 分组
    conversations: dict[str, dict] = {}

    for msg in sent + received:
        if msg.sender_id == user_id and msg.sender_role == role:
            partner_id = msg.receiver_id
            partner_role = msg.receiver_role
            is_mine = True
        else:
            partner_id = msg.sender_id
            partner_role = msg.sender_role
            is_mine = False

        key = f"{partner_role}:{partner_id}"
        if key not in conversations:
            conversations[key] = {
                "partner_id": partner_id,
                "partner_role": partner_role,
                "last_message": "",
                "last_time": None,
                "unread_count": 0,
            }

        conv = conversations[key]
        # 更新最后消息
        msg_time = msg.created_at if msg.created_at else None
        if msg_time and (conv["last_time"] is None or msg_time > conv["last_time"]):
            conv["last_message"] = msg.content[:50] if msg.content else ""
            conv["last_time"] = msg_time

        # 统计未读消息
        if not is_mine and not msg.is_read:
            conv["unread_count"] += 1

    # 构建结果列表
    result = []
    for key, conv in conversations.items():
        partner_info = _get_entity_info(conv["partner_id"], conv["partner_role"], db)
        result.append({
            "partner_id": conv["partner_id"],
            "partner_role": conv["partner_role"],
            "partner_name": partner_info.get("name", ""),
            "partner_avatar": partner_info.get("avatar", ""),
            "last_message": conv["last_message"],
            "last_time": conv["last_time"].isoformat() if conv["last_time"] else None,
            "unread_count": conv["unread_count"],
        })

    # 按最近消息时间倒序
    result.sort(key=lambda x: x["last_time"] or "", reverse=True)

    return success_response(data=result)


# ──────────────────────────── 消息历史 ────────────────────────────


@router.get("/{target_role}/{target_id}", summary="消息历史")
def get_message_history(
    target_role: str,
    target_id: int,
    user_id: int = Query(..., description="当前用户ID"),
    role: str = Query(..., pattern="^(user|merchant|delivery)$", description="当前角色"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(30, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """
    获取当前用户与指定目标用户之间的消息历史（分页）。
    请求示例：GET /messages/merchant/1?user_id=2&role=user
    """
    messages = (
        db.query(Message)
        .filter(
            or_(
                (Message.sender_id == user_id) & (Message.sender_role == role) &
                (Message.receiver_id == target_id) & (Message.receiver_role == target_role),
                (Message.sender_id == target_id) & (Message.sender_role == target_role) &
                (Message.receiver_id == user_id) & (Message.receiver_role == role),
            )
        )
        .order_by(Message.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    total = (
        db.query(Message)
        .filter(
            or_(
                (Message.sender_id == user_id) & (Message.sender_role == role) &
                (Message.receiver_id == target_id) & (Message.receiver_role == target_role),
                (Message.sender_id == target_id) & (Message.sender_role == target_role) &
                (Message.receiver_id == user_id) & (Message.receiver_role == role),
            )
        )
        .count()
    )

    items = []
    for msg in reversed(messages):  # 反转以便按时间正序显示
        items.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_role": msg.sender_role,
            "receiver_id": msg.receiver_id,
            "receiver_role": msg.receiver_role,
            "content": msg.content,
            "message_type": msg.message_type,
            "is_read": msg.is_read,
            "order_id": msg.order_id,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    # 自动标记对方发来的未读消息为已读
    unread_from_target = (
        db.query(Message)
        .filter(
            Message.sender_id == target_id,
            Message.sender_role == target_role,
            Message.receiver_id == user_id,
            Message.receiver_role == role,
            Message.is_read == False,
        )
        .all()
    )
    now_utc = datetime.now(timezone.utc)
    for msg in unread_from_target:
        msg.is_read = True
        msg.read_at = now_utc
    if unread_from_target:
        db.commit()

    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 发送消息 ────────────────────────────


@router.post("", summary="发送消息")
def send_message(
    req: SendMessageRequest,
    sender_id: int = Query(..., description="发送者ID"),
    sender_role: str = Query(..., pattern="^(user|merchant|delivery)$", description="发送者角色"),
    db: Session = Depends(get_db),
):
    """
    发送一条消息给指定接收者。
    请求示例：POST /messages?sender_id=1&sender_role=user
    """
    # 校验接收者存在
    partner_info = _get_entity_info(req.receiver_id, req.receiver_role, db)
    if not partner_info.get("phone"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接收者不存在")

    now_utc = datetime.now(timezone.utc)
    message = Message(
        sender_id=sender_id,
        sender_role=sender_role,
        receiver_id=req.receiver_id,
        receiver_role=req.receiver_role,
        content=req.content,
        order_id=req.order_id,
        message_type="text",
        is_read=False,
    )
    message.created_at = now_utc
    message.updated_at = now_utc
    db.add(message)
    db.commit()
    db.refresh(message)

    return success_response(
        data={
            "id": message.id,
            "sender_id": message.sender_id,
            "sender_role": message.sender_role,
            "receiver_id": message.receiver_id,
            "receiver_role": message.receiver_role,
            "content": message.content,
            "message_type": message.message_type,
            "is_read": message.is_read,
            "order_id": message.order_id,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        },
        message="发送成功",
    )


# ──────────────────────────── 标记已读 ────────────────────────────


@router.put("/{message_id}/read", summary="标记已读")
def mark_as_read(
    message_id: int,
    db: Session = Depends(get_db),
):
    """将指定消息标记为已读"""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")

    msg.is_read = True
    msg.read_at = datetime.now(timezone.utc)
    db.commit()

    return success_response(message="已标记为已读")


# ──────────────────────────── 未读消息数 ────────────────────────────


@router.get("/unread-count", summary="未读消息数")
def unread_count(
    user_id: int = Query(..., description="当前用户ID"),
    role: str = Query(..., pattern="^(user|merchant|delivery)$", description="当前角色"),
    db: Session = Depends(get_db),
):
    """获取当前用户的未读消息总数"""
    count = (
        db.query(Message)
        .filter(
            Message.receiver_id == user_id,
            Message.receiver_role == role,
            Message.is_read == False,
        )
        .count()
    )
    return success_response(data={"unread_count": count})
