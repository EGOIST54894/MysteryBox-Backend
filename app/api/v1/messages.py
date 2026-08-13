"""
消息系统 API 端点

支持用户/商家/配送员三端消息互通（使用 JWT Token 认证）：
- GET    /messages/conversations  会话列表
- GET    /messages/{target_role}/{target_id}  消息历史
- POST   /messages                发送消息
- PUT    /messages/{id}/read      标记已读
- GET    /messages/unread-count   未读消息数
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.dependencies import get_current_any_user, get_db
from app.models.delivery import DeliveryPersonnel
from app.models.merchant import Merchant
from app.models.message import Message
from app.models.order import Order
from app.models.mystery_box import MysteryBox
from app.models.user import User
from app.utils.response import paginated_response, success_response

router = APIRouter()


class SendMessageRequest(BaseModel):
    """发送消息请求（1v1 或群聊）"""
    receiver_id: int = Field(0, description="接收者ID（群聊时忽略）")
    receiver_role: str = Field("user", pattern="^(user|merchant|delivery|all)$", description="接收者角色")
    content: str = Field(..., min_length=1, max_length=2000, description="消息内容")
    order_id: int | None = Field(None, description="关联订单ID")
    is_group: bool = Field(False, description="是否为群聊消息（true 时忽略 receiver，发到订单群聊）")


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


def get_order_participants(order_id: int, db: Session) -> list[dict]:
    """
    获取订单的所有参与者。

    返回 [{role: str, id: int, name: str}, ...]，
    包含 user（买家）、merchant（商家）、delivery（骑手，如果已接单）。
    """
    participants: list[dict] = []

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return participants

    # 用户（买家）
    user = db.query(User).filter(User.id == order.user_id).first()
    if user:
        participants.append({
            "role": "user",
            "id": user.id,
            "name": user.nickname or f"用户{user.phone[-4:]}" if user.phone else f"用户{user.id}",
        })

    # 商家（通过盲盒）
    box = order.mystery_box
    if box:
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        if merchant:
            participants.append({
                "role": "merchant",
                "id": merchant.id,
                "name": merchant.nickname or merchant.store_name,
            })

    # 骑手（通过配送单）
    delivery_order = order.delivery_order
    if delivery_order:
        dp = delivery_order.delivery_person
        if dp:
            participants.append({
                "role": "delivery",
                "id": dp.id,
                "name": dp.nickname or dp.real_name or f"配送员{dp.id}",
            })

    return participants


# ──────────────────────────── 会话列表 ────────────────────────────


@router.get("/conversations", summary="会话列表")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_any_user),
):
    """
    获取当前用户的会话列表（包含 1v1 私聊和订单群聊）。
    认证方式：Bearer Token（支持 user/merchant/delivery 三种角色）
    """
    user_id = int(current_user["sub"])
    role = current_user["role"]

    # 加载所有与当前用户相关的消息
    sent = (
        db.query(Message)
        .filter(Message.sender_id == user_id, Message.sender_role == role)
        .all()
    )
    received = (
        db.query(Message)
        .filter(Message.receiver_id == user_id, Message.receiver_role == role)
        .all()
    )
    all_msgs: list[tuple[Message, bool]] = []
    for msg in sent:
        all_msgs.append((msg, True))   # is_mine = True
    for msg in received:
        all_msgs.append((msg, False))  # is_mine = False

    result: list[dict] = []

    # ── 1. 1v1 私聊（不含 order_id 的消息）──
    direct_conv: dict[str, dict] = {}
    for msg, is_mine in all_msgs:
        if msg.order_id is not None:
            continue  # 订单相关的消息归入群聊

        if is_mine:
            partner_id = msg.receiver_id
            partner_role = msg.receiver_role
        else:
            partner_id = msg.sender_id
            partner_role = msg.sender_role

        # 跳过 receiver_role='all' 的群聊消息
        if partner_role == "all" or partner_id == 0:
            continue

        key = f"{partner_role}:{partner_id}"
        if key not in direct_conv:
            direct_conv[key] = {
                "partner_id": partner_id,
                "partner_role": partner_role,
                "last_message": "",
                "last_time": None,
                "unread_count": 0,
            }
        conv = direct_conv[key]
        msg_time = msg.created_at if msg.created_at else None
        if msg_time and (conv["last_time"] is None or msg_time > conv["last_time"]):
            conv["last_message"] = (msg.content or "")[:50]
            conv["last_time"] = msg_time
        if not is_mine and not msg.is_read:
            conv["unread_count"] += 1

    for _key, conv in direct_conv.items():
        partner_info = _get_entity_info(conv["partner_id"], conv["partner_role"], db)
        result.append({
            "conversation_type": "direct",
            "partner_id": conv["partner_id"],
            "partner_role": conv["partner_role"],
            "partner_name": partner_info.get("name", ""),
            "partner_avatar": partner_info.get("avatar", ""),
            "last_message": conv["last_message"],
            "last_time": conv["last_time"].isoformat() if conv["last_time"] else None,
            "unread_count": conv["unread_count"],
            "order_id": 0,
            "order_no": "",
            "group_name": "",
        })

    # ── 2. 订单群聊（有 order_id 的消息，按订单聚合）──
    # 收集所有涉及的 order_id
    order_ids: set[int] = set()
    for msg, _is_mine in all_msgs:
        if msg.order_id is not None:
            order_ids.add(msg.order_id)
    # 也检查 receiver_role='all' 的消息
    group_msgs = (
        db.query(Message)
        .filter(Message.order_id.isnot(None), Message.receiver_role == "all")
        .all()
    )
    for gm in group_msgs:
        order_ids.add(gm.order_id)
        all_msgs.append((gm, gm.sender_id == user_id and gm.sender_role == role))

    # 只保留当前用户参与者的订单
    for oid in sorted(order_ids, reverse=True):
        participants = get_order_participants(oid, db)
        participant_roles = {(p["role"], p["id"]) for p in participants}
        if (role, user_id) not in participant_roles:
            continue  # 当前用户不是该订单的参与者

        # 计算该订单群聊的最后消息、未读数
        order_msgs = [(m, is_mine) for m, is_mine in all_msgs if m.order_id == oid]
        if not order_msgs:
            continue

        last_msg = None
        last_time = None
        unread = 0
        for m, is_mine in order_msgs:
            mt = m.created_at if m.created_at else None
            if mt and (last_time is None or mt > last_time):
                last_time = mt
                last_msg = m
            # 群消息（receiver_role='all'）：不是自己发的都算未读
            if m.receiver_role == "all":
                if not is_mine and not m.is_read:
                    unread += 1
            # 1v1 消息（旧数据兼容）：收到的且未读
            elif not is_mine and not m.is_read:
                unread += 1

        order = db.query(Order).filter(Order.id == oid).first()
        order_no = order.order_no if order else f"#{oid}"
        group_name = f"订单群聊 #{order_no}"

        # 成员摘要
        member_names = [p["name"] for p in participants]

        result.append({
            "conversation_type": "group",
            "partner_id": 0,
            "partner_role": "",
            "partner_name": group_name,
            "partner_avatar": "",
            "last_message": (last_msg.content or "")[:50] if last_msg else "",
            "last_time": last_time.isoformat() if last_time else None,
            "unread_count": unread,
            "order_id": oid,
            "order_no": order_no,
            "group_name": group_name,
            "members": [{"role": p["role"], "id": p["id"], "name": p["name"]} for p in participants],
        })

    result.sort(key=lambda x: x["last_time"] or "", reverse=True)
    return success_response(data=result)


# ──────────────────────────── 群聊消息历史 ────────────────────────────


@router.get("/group/{order_id}", summary="群聊消息历史")
def get_group_messages(
    order_id: int,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(30, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_any_user),
):
    """
    获取订单的群聊消息历史（分页，自动标记已读）。

    返回该订单下所有参与者可见的消息（receiver_role='all' 的群聊消息 +
    当前用户发出或收到的 1v1 消息），按时间正序显示。
    每条消息附带发送者的显示名称。
    """
    user_id = int(current_user["sub"])
    role = current_user["role"]

    # 校验当前用户是该订单的参与者
    participants = get_order_participants(order_id, db)
    participant_ids = {(p["role"], p["id"]) for p in participants}
    if (role, user_id) not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您不是该订单的参与者，无权查看群聊",
        )

    # 查询条件：order_id 匹配 + 当前用户可见
    # 可见的条件：receiver_role='all'（群聊对所有人可见）
    #            OR 当前用户是 sender
    #            OR 当前用户是 receiver（兼容旧 1v1 消息）
    base_filter = and_(
        Message.order_id == order_id,
        or_(
            Message.receiver_role == "all",
            (Message.sender_id == user_id) & (Message.sender_role == role),
            (Message.receiver_id == user_id) & (Message.receiver_role == role),
        ),
    )

    total = db.query(func.count(Message.id)).filter(base_filter).scalar() or 0

    messages = (
        db.query(Message)
        .filter(base_filter)
        .order_by(Message.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for msg in reversed(messages):
        # 解析发送者名称
        sender_info = _get_entity_info(msg.sender_id, msg.sender_role, db)
        items.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_role": msg.sender_role,
            "sender_name": sender_info.get("name", ""),
            "receiver_id": msg.receiver_id,
            "receiver_role": msg.receiver_role,
            "content": msg.content,
            "message_type": msg.message_type,
            "is_read": msg.is_read,
            "order_id": msg.order_id,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    # 自动标记未读消息为已读（收到的群消息）
    unread_msgs = (
        db.query(Message)
        .filter(
            Message.order_id == order_id,
            Message.is_read == False,
            ~and_(Message.sender_id == user_id, Message.sender_role == role),
            or_(
                Message.receiver_role == "all",
                and_(Message.receiver_id == user_id, Message.receiver_role == role),
            ),
        )
        .all()
    )
    now_utc = datetime.now(timezone.utc)
    for msg in unread_msgs:
        msg.is_read = True
        msg.read_at = now_utc
    if unread_msgs:
        db.commit()

    return paginated_response(items=items, total=total, page=page, size=size)


# ──────────────────────────── 消息历史 ────────────────────────────


@router.get("/{target_role}/{target_id}", summary="消息历史")
def get_message_history(
    target_role: str,
    target_id: int,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(30, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_any_user),
):
    """
    获取当前用户与指定目标用户之间的消息历史（分页，自动标记已读）。
    认证方式：Bearer Token
    """
    user_id = int(current_user["sub"])
    role = current_user["role"]

    base_filter = or_(
        (Message.sender_id == user_id) & (Message.sender_role == role) &
        (Message.receiver_id == target_id) & (Message.receiver_role == target_role),
        (Message.sender_id == target_id) & (Message.sender_role == target_role) &
        (Message.receiver_id == user_id) & (Message.receiver_role == role),
    )

    total = db.query(func.count(Message.id)).filter(base_filter).scalar() or 0

    messages = (
        db.query(Message)
        .filter(base_filter)
        .order_by(Message.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for msg in reversed(messages):  # 反转以按时间正序显示
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_any_user),
):
    """
    发送消息（支持 1v1 私聊和订单群聊）。

    - 群聊模式（is_group=true）：消息对所有订单参与者可见，存储为 receiver_role='all'
    - 1v1 模式（is_group=false）：消息发给指定接收者

    认证方式：Bearer Token（发送者身份从 token 中提取）
    """
    sender_id = int(current_user["sub"])
    sender_role = current_user["role"]

    if req.is_group:
        # ── 群聊模式 ──
        if not req.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="群聊消息必须指定 order_id",
            )
        # 校验当前用户是该订单的参与者
        participants = get_order_participants(req.order_id, db)
        participant_ids = {(p["role"], p["id"]) for p in participants}
        if (sender_role, sender_id) not in participant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不是该订单的参与者，无权发送群聊消息",
            )

        message = Message(
            sender_id=sender_id,
            sender_role=sender_role,
            receiver_id=0,
            receiver_role="all",
            content=req.content,
            order_id=req.order_id,
            message_type="text",
            is_read=False,
        )
        db.add(message)
        db.commit()
        db.refresh(message)

        return success_response(
            data={
                "id": message.id,
                "sender_id": message.sender_id,
                "sender_role": message.sender_role,
                "sender_name": _get_entity_info(sender_id, sender_role, db).get("name", ""),
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
    else:
        # ── 1v1 模式 ──
        # 校验接收者存在
        partner_info = _get_entity_info(req.receiver_id, req.receiver_role, db)
        if not partner_info.get("phone"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接收者不存在")

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
    current_user: dict = Depends(get_current_any_user),
):
    """将指定消息标记为已读（需登录）"""
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_any_user),
):
    """获取当前用户的未读消息总数（需登录）"""
    user_id = int(current_user["sub"])
    role = current_user["role"]

    count = (
        db.query(func.count(Message.id))
        .filter(
            Message.receiver_id == user_id,
            Message.receiver_role == role,
            Message.is_read == False,
        )
        .scalar()
    ) or 0

    return success_response(data={"unread_count": count})
