"""
配送业务逻辑模块

包含配送员接单、取餐、送达、位置更新、订单查询、统计等核心配送业务。
配送流程:
    1. 配送员查看附近待接订单 (paid)
    2. 配送员接单 (创建 DeliveryOrder, Order 状态 -> confirmed)
    3. 商家备货完成后配送员取餐 (DeliveryOrder 状态 -> picked_up)
    4. 配送员送达 (DeliveryOrder 状态 -> delivered, Order 状态 -> delivered)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.delivery import DeliveryPersonnel
from app.models.merchant import Merchant
from app.models.mystery_box import MysteryBox
from app.models.order import DeliveryOrder, Order
from app.models.user import UserAddress
from app.services.order_service import _validate_status_transition
from app.utils.geo import format_distance, haversine_distance


def get_available_orders(
    lat: float,
    lng: float,
    radius: float = 5000,
    db: Session = None,
) -> list:
    """
    获取配送员附近可接的订单列表。

    筛选条件：
    1. 订单状态为 paid（已支付，待配送员接单）
    2. 该订单尚未被任何配送员接单（无 DeliveryOrder 记录）
    3. 商家有有效的经纬度坐标

    按配送员当前位置到商家（取餐点）的距离升序排列。

    Args:
        lat: 配送员当前纬度
        lng: 配送员当前经度
        radius: 搜索半径（米），默认 5000m
        db: 数据库会话

    Returns:
        可接订单列表，每项包含订单详情、商家信息、用户地址、距离等
    """
    # 查询所有 ready_pickup 且未被接单的订单
    # 通过 LEFT JOIN 检查 delivery_order 表中是否已有该订单的配送记录
    subquery = (
        db.query(DeliveryOrder.order_id)
        .subquery()
    )

    orders = (
        db.query(Order)
        .filter(
            Order.order_status == "paid",
            ~Order.id.in_(subquery),
        )
        .all()
    )

    available = []

    for order in orders:
        # 获取商家坐标（通过盲盒关联商家）
        box = order.mystery_box
        if not box:
            continue

        merchant = box.merchant
        if not merchant or merchant.latitude is None or merchant.longitude is None:
            # 商家未设置坐标，跳过
            continue

        # 计算配送员到商家（取餐点）的距离
        distance_to_merchant = haversine_distance(
            lat, lng,
            float(merchant.latitude), float(merchant.longitude),
        )

        # 获取用户收货地址
        address = order.address
        user_lat = float(address.latitude) if address and address.latitude else None
        user_lng = float(address.longitude) if address and address.longitude else None

        # 计算商家到用户收货地址的距离
        delivery_distance = None
        if user_lat is not None and user_lng is not None:
            delivery_distance = haversine_distance(
                float(merchant.latitude), float(merchant.longitude),
                user_lat, user_lng,
            )

        available.append({
            "order_id": order.id,
            "order_no": order.order_no,
            "quantity": order.quantity,
            "total_amount": order.total_amount,
            "paid_amount": order.paid_amount,
            # 盲盒信息
            "box": {
                "id": box.id,
                "title": box.title,
                "cover_image": box.cover_image,
                "box_type": box.box_type,
            },
            # 商家信息（取餐点）
            "merchant": {
                "id": merchant.id,
                "store_name": merchant.store_name,
                "latitude": float(merchant.latitude),
                "longitude": float(merchant.longitude),
                "address": merchant.address_detail,
                "phone": getattr(merchant, "phone", ""),
            },
            # 用户收货地址
            "address": {
                "id": address.id if address else None,
                "contact_name": address.contact_name if address else "",
                "contact_phone": address.contact_phone if address else "",
                "latitude": user_lat,
                "longitude": user_lng,
                "detail": f"{address.province}{address.city}{address.district}{address.detail}" if address else "",
            } if address else None,
            # 距离信息
            "distance_to_merchant": round(distance_to_merchant, 1),          # 配送员到商家距离（米）
            "distance_to_merchant_text": format_distance(distance_to_merchant),  # 人类可读格式
            "delivery_distance": round(delivery_distance, 1) if delivery_distance else None,  # 商家到用户距离（米）
            "delivery_distance_text": format_distance(delivery_distance) if delivery_distance else None,
            # 时间信息
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        })

    # 按距离排序（先按配送员到商家距离）
    available.sort(key=lambda x: x["distance_to_merchant"])

    # 可选：只返回半径范围内的订单
    if radius > 0:
        available = [o for o in available if o["distance_to_merchant"] <= radius]

    return available


def accept_order(
    delivery_person_id: int,
    order_id: int,
    db: Session,
) -> DeliveryOrder:
    """
    配送员接单。

    流程：
    1. 校验配送员状态（必须是 1-在线 状态）
    2. 校验订单状态（必须是 paid 且未被其他人接单）
    3. 创建 DeliveryOrder 记录
    4. 更新订单状态为 confirmed
    5. 更新配送员状态为在线

    Args:
        delivery_person_id: 配送员ID
        order_id: 订单ID
        db: 数据库会话

    Returns:
        新创建的 DeliveryOrder 实例

    Raises:
        ValueError: 配送员状态异常、订单不存在、订单已被接单等情况
    """
    # 1. 校验配送员
    delivery_person = (
        db.query(DeliveryPersonnel)
        .filter(DeliveryPersonnel.id == delivery_person_id)
        .first()
    )
    if not delivery_person:
        raise ValueError("配送员不存在")
    if delivery_person.status != 1:  # 1=在线
        status_map = {0: "待审核", 2: "离线", 3: "禁用"}
        desc = status_map.get(delivery_person.status, "未知")
        raise ValueError(f"配送员当前状态为「{desc}」，无法接单。请先切换为在线状态")

    # 2. 校验订单
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("订单不存在")
    if order.order_status != "paid":
        raise ValueError(f"订单当前状态为 '{order.order_status}'，无法接单。仅已支付订单可被接单")

    # 3. 检查是否已被其他配送员接单（DeliveryOrder 的 order_id 唯一）
    existing = (
        db.query(DeliveryOrder)
        .filter(DeliveryOrder.order_id == order_id)
        .first()
    )
    if existing:
        raise ValueError("该订单已被其他配送员接单")

    # 4. 校验状态流转
    _validate_status_transition(order.order_status, "confirmed")

    # 5. 创建配送记录
    now = datetime.now(timezone.utc)
    delivery_order = DeliveryOrder(
        order_id=order_id,
        delivery_person_id=delivery_person_id,
        status="assigned",  # 配送初始状态：已分配
        assigned_at=now,
    )
    db.add(delivery_order)

    # 6. 更新订单状态为已确认（配送员已接单）
    order.order_status = "confirmed"

    # 7. 确保配送员状态为在线
    if delivery_person.status != 1:
        delivery_person.status = 1

    # 8. 自动创建群聊消息：通知所有订单参与者
    from app.models.message import Message
    dp_name = delivery_person.nickname or delivery_person.real_name or f"配送员{delivery_person_id}"

    group_msg = Message(
        sender_id=delivery_person_id,
        sender_role="delivery",
        receiver_id=0,
        receiver_role="all",
        order_id=order_id,
        content=f"🛵 {dp_name}已接单，正在前往商家取餐。如有问题可在此联系配送员。",
        message_type="system",
    )
    db.add(group_msg)

    db.commit()
    db.refresh(delivery_order)
    return delivery_order


def pickup_order(
    delivery_person_id: int,
    order_id: int,
    db: Session,
) -> DeliveryOrder:
    """
    配送员确认取餐。

    流程：
    1. 校验 DeliveryOrder 记录存在且属于该配送员
    2. 更新 DeliveryOrder 状态为 picked_up
    3. 记录 picked_up_at 时间

    Args:
        delivery_person_id: 配送员ID
        order_id: 订单ID
        db: 数据库会话

    Returns:
        更新后的 DeliveryOrder 实例

    Raises:
        ValueError: 配送记录不存在、无权操作、状态不允许
    """
    delivery_order = (
        db.query(DeliveryOrder)
        .filter(
            DeliveryOrder.order_id == order_id,
            DeliveryOrder.delivery_person_id == delivery_person_id,
        )
        .first()
    )
    if not delivery_order:
        raise ValueError("未找到该订单的配送记录，或该订单不属于您")

    if delivery_order.status != "assigned":
        raise ValueError(f"当前配送状态为 '{delivery_order.status}'，无法确认取餐。请先接单")

    now = datetime.now(timezone.utc)
    delivery_order.status = "picked_up"
    delivery_order.picked_up_at = now

    # 通知用户和商家：配送员已取餐（群聊消息）
    from app.models.message import Message
    order = delivery_order.order
    dp = delivery_order.delivery_person
    dp_name = dp.nickname or dp.real_name if dp else f"配送员{delivery_person_id}"

    if order:
        group_msg = Message(
            sender_id=delivery_person_id,
            sender_role="delivery",
            receiver_id=0,
            receiver_role="all",
            order_id=order_id,
            content=f"✅ {dp_name}已取餐，正在为您配送中。",
            message_type="system",
        )
        db.add(group_msg)

    db.commit()
    db.refresh(delivery_order)
    return delivery_order


def deliver_order(
    delivery_person_id: int,
    order_id: int,
    db: Session,
) -> DeliveryOrder:
    """
    配送员确认送达。

    流程：
    1. 校验 DeliveryOrder 记录存在且属于该配送员
    2. 更新 DeliveryOrder 状态为 delivered
    3. 记录 delivered_at 时间
    4. 更新订单状态为 delivered
    5. 更新配送员 completed_orders 计数

    Args:
        delivery_person_id: 配送员ID
        order_id: 订单ID
        db: 数据库会话

    Returns:
        更新后的 DeliveryOrder 实例

    Raises:
        ValueError: 配送记录不存在、无权操作、状态不允许
    """
    delivery_order = (
        db.query(DeliveryOrder)
        .filter(
            DeliveryOrder.order_id == order_id,
            DeliveryOrder.delivery_person_id == delivery_person_id,
        )
        .first()
    )
    if not delivery_order:
        raise ValueError("未找到该订单的配送记录，或该订单不属于您")

    if delivery_order.status not in ("picked_up", "assigned"):
        raise ValueError(f"当前配送状态为 '{delivery_order.status}'，无法确认送达。请先取餐")

    order = delivery_order.order
    if not order:
        raise ValueError("关联订单不存在")

    # 校验订单状态流转
    _validate_status_transition(order.order_status, "delivered")

    now = datetime.now(timezone.utc)

    # 更新配送记录
    delivery_order.status = "delivered"
    delivery_order.delivered_at = now

    # 更新订单状态
    order.order_status = "delivered"
    order.delivered_at = now

    # 更新配送员累计完成数
    delivery_person = delivery_order.delivery_person
    if delivery_person:
        delivery_person.completed_orders = (delivery_person.completed_orders or 0) + 1

    # 通知用户和商家：配送员已送达（群聊消息）
    from app.models.message import Message
    dp = delivery_person
    dp_name = dp.nickname or dp.real_name if dp else f"配送员{delivery_person_id}"

    if order:
        group_msg = Message(
            sender_id=delivery_person_id,
            sender_role="delivery",
            receiver_id=0,
            receiver_role="all",
            order_id=order_id,
            content=f"🏁 {dp_name}已送达，请确认收货。如有问题可联系配送员。",
            message_type="system",
        )
        db.add(group_msg)

    db.commit()
    db.refresh(delivery_order)
    return delivery_order


def update_location(
    delivery_person_id: int,
    lat: float,
    lng: float,
    db: Session,
) -> DeliveryPersonnel:
    """
    更新配送员实时位置。

    Args:
        delivery_person_id: 配送员ID
        lat: 当前纬度
        lng: 当前经度
        db: 数据库会话

    Returns:
        更新后的 DeliveryPersonnel 实例

    Raises:
        ValueError: 配送员不存在
    """
    delivery_person = (
        db.query(DeliveryPersonnel)
        .filter(DeliveryPersonnel.id == delivery_person_id)
        .first()
    )
    if not delivery_person:
        raise ValueError("配送员不存在")

    delivery_person.current_lat = lat
    delivery_person.current_lng = lng

    db.commit()
    db.refresh(delivery_person)
    return delivery_person


def get_delivery_orders(
    delivery_person_id: int,
    status_filter: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    db: Session = None,
) -> tuple[list, int]:
    """
    获取配送员的配送订单列表，支持状态筛选和分页。

    Args:
        delivery_person_id: 配送员ID
        status_filter: 可选的状态筛选（assigned / picked_up / delivered）
        page: 页码（从 1 开始）
        size: 每页条数
        db: 数据库会话

    Returns:
        (配送订单列表, 总条数)
    """
    query = (
        db.query(DeliveryOrder)
        .filter(DeliveryOrder.delivery_person_id == delivery_person_id)
    )

    if status_filter:
        query = query.filter(DeliveryOrder.status == status_filter)

    total = query.count()
    items = (
        query
        .order_by(DeliveryOrder.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # 转换为字典列表，附带订单和地址信息
    result = []
    for delivery in items:
        order = delivery.order
        box = order.mystery_box if order else None
        merchant = box.merchant if box else None
        address = order.address if order else None

        item = {
            "id": delivery.id,
            "order_id": delivery.order_id,
            "delivery_person_id": delivery.delivery_person_id,
            "status": delivery.status,
            "assigned_at": delivery.assigned_at.isoformat() if delivery.assigned_at else None,
            "picked_up_at": delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
        }

        if order:
            item["order"] = {
                "id": order.id,
                "order_no": order.order_no,
                "order_status": order.order_status,
                "total_amount": order.total_amount,
                "paid_amount": order.paid_amount,
                "quantity": order.quantity,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            }

        if box:
            item["box"] = {
                "id": box.id,
                "title": box.title,
                "cover_image": box.cover_image,
                "box_type": box.box_type,
            }

        if merchant:
            item["merchant"] = {
                "id": merchant.id,
                "store_name": merchant.store_name,
                "latitude": float(merchant.latitude) if merchant.latitude else None,
                "longitude": float(merchant.longitude) if merchant.longitude else None,
                "address": merchant.address_detail,
            }

        if address:
            item["address"] = {
                "id": address.id,
                "contact_name": address.contact_name,
                "contact_phone": address.contact_phone,
                "latitude": float(address.latitude) if address.latitude else None,
                "longitude": float(address.longitude) if address.longitude else None,
                "detail": f"{address.province}{address.city}{address.district}{address.detail}",
            }

        result.append(item)

    return result, total


def get_delivery_statistics(
    delivery_person_id: int,
    db: Session,
) -> dict:
    """
    获取配送员今日及累计配送统计数据。

    Args:
        delivery_person_id: 配送员ID
        db: 数据库会话

    Returns:
        统计信息字典，包含：
        - today_assigned: 今日接单数
        - today_completed: 今日完成数（送达数）
        - total_completed: 累计完成数
        - today_income: 今日收入（元）
        - rating_avg: 平均评分
    """
    delivery_person = (
        db.query(DeliveryPersonnel)
        .filter(DeliveryPersonnel.id == delivery_person_id)
        .first()
    )
    if not delivery_person:
        raise ValueError("配送员不存在")

    # 今日起止时间（使用 UTC）
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 今日接单数（assigned_at 在今日）
    today_assigned = (
        db.query(DeliveryOrder)
        .filter(
            DeliveryOrder.delivery_person_id == delivery_person_id,
            DeliveryOrder.assigned_at >= today_start,
        )
        .count()
    )

    # 今日完成数（delivered_at 在今日）
    today_completed = (
        db.query(DeliveryOrder)
        .filter(
            DeliveryOrder.delivery_person_id == delivery_person_id,
            DeliveryOrder.status == "delivered",
            DeliveryOrder.delivered_at >= today_start,
        )
        .count()
    )

    # 今日收入：从今日已送达的配送订单中，汇总关联订单的实付金额
    # 注：此处将实付金额视为收入（实际场景中可能需要根据业务规则调整分成比例）
    today_income_result = (
        db.query(Order.paid_amount)
        .join(DeliveryOrder, DeliveryOrder.order_id == Order.id)
        .filter(
            DeliveryOrder.delivery_person_id == delivery_person_id,
            DeliveryOrder.status == "delivered",
            DeliveryOrder.delivered_at >= today_start,
        )
        .all()
    )
    today_income = sum(float(row[0]) for row in today_income_result if row[0])

    return {
        "today_assigned": today_assigned,
        "today_completed": today_completed,
        "total_completed": delivery_person.completed_orders or 0,
        "today_income": round(today_income, 2),
        "rating_avg": float(delivery_person.rating_avg or 0),
    }
