"""
订单业务逻辑模块

包含完整的订单状态机、拼团逻辑、库存管理等核心业务。
订单状态流转规则:
    pending_pay -> paid (支付成功) / cancelled (超时取消)
    paid -> confirmed (商家确认) / cancelled (用户取消)
    confirmed -> preparing (商家开始备货)
    preparing -> ready_pickup (备货完成)
    ready_pickup -> delivering (配送员取餐)
    delivering -> delivered (配送员送达)
    delivered -> completed (用户确认收货)
    Any active state -> refunding (申请退款)
    refunding -> refunded (退款成功)
"""

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.mystery_box import MysteryBox
from app.models.order import DeliveryOrder, GroupBuyGroup, Order
from app.models.payment import PaymentRecord


# ──────────────────────────── 订单状态流转规则 ────────────────────────────

# 合法的状态流转映射：当前状态 -> 允许转换到的目标状态集合
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending_pay": {"paid", "cancelled", "refunding"},
    "paid": {"confirmed", "cancelled", "refunding"},
    "confirmed": {"preparing", "refunding"},
    "preparing": {"ready_pickup", "refunding"},
    "ready_pickup": {"delivering", "refunding"},
    "delivering": {"delivered", "refunding"},
    "delivered": {"completed", "refunding"},
    "completed": set(),       # 终态，不可再变更
    "cancelled": set(),       # 终态
    "refunding": {"refunded"},
    "refunded": set(),        # 终态
}

# 商家端允许的操作映射：当前状态 -> 下一状态（商家只能推进，不能回退）
MERCHANT_NEXT_STATUS: dict[str, str] = {
    "paid": "confirmed",
    "confirmed": "preparing",
    "preparing": "ready_pickup",
}


def _generate_order_no() -> str:
    """生成订单号：ord + 时间戳 + 6位随机数字"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = "".join(random.choices(string.digits, k=6))
    return f"ord{timestamp}{random_part}"


def _validate_status_transition(current_status: str, target_status: str) -> None:
    """
    校验订单状态流转是否合法。
    若不允许从当前状态跳转到目标状态，抛出 ValueError。
    """
    allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ValueError(
            f"订单状态不允许从 '{current_status}' 变更为 '{target_status}'。"
            f"允许的目标状态: {allowed or '无（已到达终态）'}"
        )


# ──────────────────────────── 拼团辅助函数 ────────────────────────────


def _join_or_create_group(
    order: Order, box: MysteryBox, user_id: int, existing_group_id: Optional[int], db: Session
) -> Optional[GroupBuyGroup]:
    """
    拼团盲盒下单时，自动加入已有拼团或创建新拼团。

    - 若传入了 group_id，则尝试加入已有拼团
    - 否则查找是否有可加入的进行中拼团
    - 都没有则创建一个新的拼团
    - 拼团满员后自动将团状态更新为 completed

    Returns:
        关联的 GroupBuyGroup 实例，若不是拼团类型则返回 None
    """
    # 仅拼团类型的盲盒才处理拼团逻辑
    if box.box_type != "group_buy":
        return None

    if box.group_min_size <= 0 or box.group_max_size <= 0:
        raise ValueError("拼团盲盒未配置拼团人数上下限")

    now = datetime.now(timezone.utc)

    if existing_group_id:
        # 加入已有拼团
        group = db.query(GroupBuyGroup).filter(
            GroupBuyGroup.id == existing_group_id,
            GroupBuyGroup.status == "gathering",
        ).first()
        if not group:
            raise ValueError("该拼团不存在或已结束")
        if group.current_size >= group.target_size:
            raise ValueError("该拼团已满员")
        if group.deadline and group.deadline < now:
            group.status = "expired"
            db.commit()
            raise ValueError("该拼团已过期")

        group.current_size += 1
        order.group_role = "member"

        # 检查是否满员
        if group.current_size >= group.target_size:
            group.status = "completed"
            group.completed_at = now
        db.commit()
        return group
    else:
        # 查找可加入的进行中拼团（优先找人数最多的，尽快成团）
        available_group = (
            db.query(GroupBuyGroup)
            .filter(
                GroupBuyGroup.box_id == box.id,
                GroupBuyGroup.status == "gathering",
                GroupBuyGroup.current_size < GroupBuyGroup.target_size,
            )
            .order_by(GroupBuyGroup.current_size.desc())
            .first()
        )
        if available_group:
            available_group.current_size += 1
            order.group_role = "member"
            if available_group.current_size >= available_group.target_size:
                available_group.status = "completed"
                available_group.completed_at = now
            db.commit()
            return available_group
        else:
            # 创建新拼团
            target_size = random.randint(box.group_min_size, box.group_max_size)
            # 拼团截止时间：默认24小时后或使用盲盒配置的 group_deadline
            deadline = box.group_deadline or (now + timedelta(hours=24))
            group = GroupBuyGroup(
                box_id=box.id,
                leader_user_id=user_id,
                current_size=1,
                target_size=target_size,
                status="gathering",
                deadline=deadline,
            )
            db.add(group)
            db.flush()  # 获取 group.id
            order.group_role = "leader"
            return group


# ──────────────────────────── 创建订单 ────────────────────────────


def create_order(user_id: int, data, db: Session) -> Order:
    """
    创建订单。

    流程：
    1. 校验盲盒状态和库存
    2. 扣减库存（若库存归零则设为售罄状态）
    3. 计算订单金额
    4. 处理拼团逻辑（拼团类型盲盒）
    5. 创建 pending_pay 状态的订单

    Args:
        user_id: 下单用户ID
        data: OrderCreate schema 实例
        db: 数据库会话

    Returns:
        新创建的 Order 实例

    Raises:
        ValueError: 盲盒不存在、已下架、库存不足等情况
    """
    # 1. 查询并校验盲盒
    box = db.query(MysteryBox).filter(MysteryBox.id == data.box_id).first()
    if not box:
        raise ValueError("盲盒不存在")
    if box.status not in (1,):  # 1=上架，其他状态不可购买
        status_map = {0: "已下架", 2: "已售罄", 3: "已过期"}
        raise ValueError(f"该盲盒{status_map.get(box.status, '不可购买')}")
    if box.stock < data.quantity:
        raise ValueError(f"库存不足，当前库存: {box.stock}")

    # 2. 计算金额
    unit_price = float(box.sale_price)
    total_amount = unit_price * data.quantity
    paid_amount = total_amount  # 实付金额（简化处理，暂无优惠逻辑）

    # 3. 扣减库存
    box.stock -= data.quantity
    box.sale_count += data.quantity
    if box.stock == 0:
        box.status = 2  # 售罄

    # 4. 生成订单（address_id 为可选，允许不传地址直接下单）
    order_no = _generate_order_no()
    order = Order(
        order_no=order_no,
        user_id=user_id,
        box_id=data.box_id,
        address_id=data.address_id if data.address_id else None,
        quantity=data.quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        discount_amount=0.00,
        paid_amount=paid_amount,
        order_status="pending_pay",
    )
    db.add(order)
    db.flush()  # 获取 order.id 以便后续关联

    # 5. 处理拼团逻辑
    group = _join_or_create_group(order, box, user_id, data.group_id, db)
    if group:
        order.group_id = group.id

    db.commit()
    db.refresh(order)

    # 6. 自动创建订单群聊：发一条初始消息
    try:
        from app.models.message import Message

        auto_msg = Message(
            sender_id=user_id,
            sender_role="user",
            receiver_id=0,
            receiver_role="all",
            content=f"我下单了「{box.title}」，订单号 {order_no}",
            order_id=order.id,
            message_type="text",
            is_read=False,
        )
        db.add(auto_msg)
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"自动创建下单消息失败 (order_id={order.id}, user_id={user_id}): {e}"
        )

    return order


# ──────────────────────────── 查询订单详情 ────────────────────────────


def get_order_detail(order_id: int, user_id: int, db: Session) -> dict:
    """
    获取订单详情，包含盲盒信息、地址信息、配送状态。

    Args:
        order_id: 订单主键ID
        user_id: 当前用户ID（用于权限校验）
        db: 数据库会话

    Returns:
        订单详情字典

    Raises:
        ValueError: 订单不存在或无权查看
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")
    if order.user_id != user_id:
        raise ValueError("无权查看该订单")

    # 构造返回数据（同时包含扁平字段和嵌套字段，兼容前端各页面）
    result = {
        "id": order.id,
        "order_no": order.order_no,
        "user_id": order.user_id,
        "box_id": order.box_id,
        "address_id": order.address_id,
        "quantity": order.quantity,
        "unit_price": float(order.unit_price),
        "total_amount": float(order.total_amount),
        "discount_amount": float(order.discount_amount),
        "paid_amount": float(order.paid_amount),
        "actual_price": float(order.paid_amount if order.paid_amount else order.total_amount),
        "group_id": order.group_id,
        "group_role": order.group_role,
        "status": order.order_status,
        "order_status": order.order_status,
        "cancel_reason": order.cancel_reason,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }

    # 盲盒信息（嵌套 + 扁平）
    box = order.mystery_box
    if box:
        result["box"] = {
            "id": box.id,
            "title": box.title,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
        }
        result["box_title"] = box.title
        result["box_cover"] = box.cover_image
        result["box_type"] = box.box_type
        result["original_price"] = float(box.original_price) if box.original_price else 0
        result["box_price"] = float(box.sale_price) if box.sale_price else 0
        # 商家信息扁平
        if box.merchant:
            result["merchant_id"] = box.merchant.id
            result["merchant_name"] = box.merchant.store_name or ""
            result["merchant_phone"] = box.merchant.phone or ""
            result["pickup_address"] = box.merchant.address_detail or ""

    # 地址信息
    addr = order.address
    if addr:
        result["address"] = {
            "id": addr.id,
            "contact_name": addr.contact_name,
            "contact_phone": addr.contact_phone,
            "province": addr.province,
            "city": addr.city,
            "district": addr.district,
            "detail": addr.detail,
        }

    # 配送信息
    delivery = order.delivery_order
    if delivery:
        result["delivery"] = {
            "id": delivery.id,
            "status": delivery.status,
            "delivery_person_id": delivery.delivery_person_id,
            "assigned_at": delivery.assigned_at.isoformat() if delivery.assigned_at else None,
            "picked_up_at": delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        }
    else:
        result["delivery"] = None

    # 拼团信息
    group = order.group_buy_group
    if group:
        result["group_info"] = {
            "id": group.id,
            "current_size": group.current_size,
            "target_size": group.target_size,
            "status": group.status,
            "deadline": group.deadline.isoformat() if group.deadline else None,
        }

    return result


# ──────────────────────────── 用户订单列表 ────────────────────────────


def get_user_orders(
    user_id: int,
    status_filter: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    db: Session = None,
) -> tuple[list, int]:
    """
    获取用户订单列表，支持状态筛选和分页。

    Args:
        user_id: 用户ID
        status_filter: 可选的状态筛选
        page: 页码（从1开始）
        size: 每页条数
        db: 数据库会话

    Returns:
        (订单列表, 总条数)
    """
    query = db.query(Order).filter(Order.user_id == user_id)
    if status_filter:
        # 支持逗号分隔的多状态筛选（如 pending_pay,paid,confirmed）
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.filter(Order.order_status == statuses[0])
        else:
            query = query.filter(Order.order_status.in_(statuses))

    total = query.count()
    items = (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # 转换为字典列表（扁平化字段，匹配前端 OrderInfo 接口）
    result = []
    for order in items:
        box = order.mystery_box
        merchant_name = ""
        if box and box.merchant:
            merchant_name = box.merchant.store_name or ""
        item = {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "box_id": order.box_id,
            "box_title": box.title if box else "",
            "box_cover": box.cover_image if box else "",
            "box_type": box.box_type if box else "",
            "merchant_name": merchant_name,
            "merchant_id": box.merchant_id if box else 0,
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "actual_price": float(order.paid_amount if order.paid_amount else order.total_amount),
            "group_id": order.group_id,
            "group_role": order.group_role,
            "status": order.order_status,
            "order_status": order.order_status,
            "cancel_reason": order.cancel_reason,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }
        result.append(item)

    return result, total


# ──────────────────────────── 取消订单 ────────────────────────────


def cancel_order(order_id: int, user_id: int, reason: Optional[str], db: Session) -> Order:
    """
    用户取消订单。
    - 只能取消 pending_pay 或 paid 状态的订单
    - 如果是 pending_pay 状态，直接取消并恢复库存
    - 如果是 paid 状态，进入 refunding 状态等待退款

    Args:
        order_id: 订单主键ID
        user_id: 用户ID
        reason: 取消原因
        db: 数据库会话

    Returns:
        更新后的 Order 实例

    Raises:
        ValueError: 订单不存在、无权操作或状态不允许
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")
    if order.user_id != user_id:
        raise ValueError("无权操作该订单")

    now = datetime.now(timezone.utc)

    if order.order_status == "pending_pay":
        # 未支付订单直接取消，恢复库存
        _validate_status_transition(order.order_status, "cancelled")
        order.order_status = "cancelled"
        order.cancel_reason = reason or "用户主动取消"
        order.cancelled_at = now
        _restore_box_stock(order, db)
        db.commit()
        db.refresh(order)
        return order

    elif order.order_status == "paid":
        # 已支付订单进入退款流程
        _validate_status_transition(order.order_status, "cancelled")
        order.order_status = "refunding"
        order.cancel_reason = reason or "用户申请退款"
        order.cancelled_at = now
        db.commit()
        db.refresh(order)
        return order

    else:
        raise ValueError(f"当前订单状态 '{order.order_status}' 不允许取消，仅待支付和已支付订单可取消")


def _restore_box_stock(order: Order, db: Session) -> None:
    """恢复订单关联的盲盒库存"""
    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if box:
        box.stock += order.quantity
        box.sale_count = max(0, box.sale_count - order.quantity)
        # 如果之前是售罄状态，恢复为上架
        if box.status == 2 and box.stock > 0:
            box.status = 1


# ──────────────────────────── 确认收货 ────────────────────────────


def confirm_receipt(order_id: int, user_id: int, db: Session) -> Order:
    """
    用户确认收货。
    只能确认 delivered 状态的订单，状态变为 completed。

    Args:
        order_id: 订单主键ID
        user_id: 用户ID
        db: 数据库会话

    Returns:
        更新后的 Order 实例
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")
    if order.user_id != user_id:
        raise ValueError("无权操作该订单")
    if order.order_status != "delivered":
        raise ValueError("只能确认已送达的订单")

    _validate_status_transition(order.order_status, "completed")
    now = datetime.now(timezone.utc)
    order.order_status = "completed"
    order.completed_at = now
    db.commit()
    db.refresh(order)
    return order


# ──────────────────────────── 商家端订单列表 ────────────────────────────


def get_merchant_orders(
    merchant_id: int,
    status_filter: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    db: Session = None,
) -> tuple[list, int]:
    """
    商家查看自己店铺的订单列表，支持状态筛选和分页。

    通过盲盒表的 merchant_id 关联查询。
    """
    query = (
        db.query(Order)
        .join(MysteryBox, Order.box_id == MysteryBox.id)
        .filter(MysteryBox.merchant_id == merchant_id)
    )
    if status_filter:
        query = query.filter(Order.order_status == status_filter)

    total = query.count()
    items = (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    result = []
    for order in items:
        item = {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "box_id": order.box_id,
            "quantity": order.quantity,
            "unit_price": order.unit_price,
            "total_amount": order.total_amount,
            "paid_amount": order.paid_amount,
            "group_id": order.group_id,
            "order_status": order.order_status,
            "cancel_reason": order.cancel_reason,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        box = order.mystery_box
        if box:
            item["box"] = {
                "id": box.id,
                "title": box.title,
                "cover_image": box.cover_image,
                "box_type": box.box_type,
            }
        # 包含用户简要信息（地址中的联系方式）
        addr = order.address
        if addr:
            item["contact"] = {
                "name": addr.contact_name,
                "phone": addr.contact_phone,
                "address": f"{addr.province}{addr.city}{addr.district}{addr.detail}",
            }
        result.append(item)

    return result, total


# ──────────────────────────── 商家确认订单 ────────────────────────────


def merchant_confirm_order(order_id: int, merchant_id: int, db: Session) -> Order:
    """
    商家确认订单: paid -> confirmed

    校验该订单对应的盲盒属于当前商家。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    # 校验商家权限：该订单的盲盒必须属于该商家
    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if not box or box.merchant_id != merchant_id:
        raise ValueError("无权操作该订单，订单不属于您的店铺")

    _validate_status_transition(order.order_status, "confirmed")
    now = datetime.now(timezone.utc)
    order.order_status = "confirmed"
    order.confirmed_at = now
    db.commit()
    db.refresh(order)
    return order


# ──────────────────────────── 商家备货完成（待取餐） ────────────────────────────


def merchant_ready_pickup(order_id: int, merchant_id: int, db: Session) -> Order:
    """
    商家标记备货完成: preparing -> ready_pickup

    校验该订单对应的盲盒属于当前商家。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    box = db.query(MysteryBox).filter(MysteryBox.id == order.box_id).first()
    if not box or box.merchant_id != merchant_id:
        raise ValueError("无权操作该订单")

    _validate_status_transition(order.order_status, "ready_pickup")
    order.order_status = "ready_pickup"
    db.commit()
    db.refresh(order)
    return order


# ──────────────────────────── 更新订单状态（通用方法） ────────────────────────────


def update_order_status(order_id: int, target_status: str, db: Session) -> Order:
    """
    通用订单状态更新方法，带状态流转校验。

    供 payment_service 等内部模块调用。

    Args:
        order_id: 订单主键ID
        target_status: 目标状态
        db: 数据库会话

    Returns:
        更新后的 Order 实例
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")

    _validate_status_transition(order.order_status, target_status)
    now = datetime.now(timezone.utc)
    order.order_status = target_status

    # 记录各状态的时间节点
    if target_status == "paid":
        order.paid_at = now
    elif target_status == "confirmed":
        order.confirmed_at = now
    elif target_status == "delivered":
        order.delivered_at = now
    elif target_status == "completed":
        order.completed_at = now
    elif target_status == "cancelled":
        order.cancelled_at = now

    db.commit()
    db.refresh(order)
    return order


# ──────────────────────────── 获取配送追踪信息 ────────────────────────────


def get_order_tracking(order_id: int, user_id: int, db: Session) -> dict:
    """
    获取订单配送追踪信息。

    Returns:
        包含配送状态、配送员信息、预计送达时间等的字典
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")
    if order.user_id != user_id:
        raise ValueError("无权查看该订单")

    delivery = order.delivery_order
    delivery_info = None
    if delivery:
        delivery_info = {
            "id": delivery.id,
            "status": delivery.status,
            "assigned_at": delivery.assigned_at.isoformat() if delivery.assigned_at else None,
            "picked_up_at": delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        }
        if delivery.delivery_person:
            delivery_info["delivery_person"] = {
                "id": delivery.delivery_person.id,
                "name": getattr(delivery.delivery_person, "name", ""),
                "phone": getattr(delivery.delivery_person, "phone", ""),
            }

    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "order_status": order.order_status,
        "delivery": delivery_info,
    }
