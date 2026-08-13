"""
盲盒业务逻辑层

提供盲盒的增删改查、列表筛选、附近盲盒、浏览计数等核心业务方法。
所有方法均通过 SQLAlchemy session 操作数据库。
"""

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session, joinedload

from app.models.merchant import Merchant
from app.models.mystery_box import BoxTag, MysteryBox
from app.schemas.mystery_box import BoxCreate, BoxUpdate, BoxListQuery
from app.utils.geo import haversine_distance


# ──────────────────────────── 盲盒创建 ────────────────────────────


def create_box(merchant_id: int, data: BoxCreate, db: Session) -> MysteryBox:
    """
    创建盲盒商品，同时创建关联的标签记录。

    Args:
        merchant_id: 商家ID
        data: 盲盒创建请求数据（Pydantic Schema）
        db: 数据库会话

    Returns:
        新创建的 MysteryBox ORM 对象
    """
    # 将 Decimal 转为 float 存储
    original_price = float(data.original_price)
    sale_price = float(data.sale_price)

    # 基础字段赋值
    box = MysteryBox(
        merchant_id=merchant_id,
        title=data.title,
        description=data.description,
        cover_image=data.cover_image,
        box_type=data.box_type,
        original_price=original_price,
        sale_price=sale_price,
        stock=data.stock,
        total_stock=data.stock,  # 创建时总库存 = 当前库存
        status=1,  # 默认上架
        pick_up_start=data.pickup_start_time,
        pick_up_end=data.pickup_end_time,
        publish_at=datetime.now(timezone.utc),
    )
    db.add(box)
    db.flush()  # 先 flush 以获取 box.id，用于创建标签

    # 创建标签关联
    if data.tags:
        for tag_name in data.tags:
            # 去重：同一个盲盒不允许重复标签
            if not tag_name or not tag_name.strip():
                continue
            tag_name = tag_name.strip()
            existing_tag = (
                db.query(BoxTag)
                .filter(BoxTag.box_id == box.id, BoxTag.tag_name == tag_name)
                .first()
            )
            if not existing_tag:
                db.add(BoxTag(box_id=box.id, tag_name=tag_name))

    db.commit()
    db.refresh(box)
    return box


# ──────────────────────────── 盲盒编辑 ────────────────────────────


def update_box(box_id: int, merchant_id: int, data: BoxUpdate, db: Session) -> MysteryBox:
    """
    编辑盲盒信息（仅允许修改自己的盲盒）。

    Args:
        box_id: 盲盒ID
        merchant_id: 商家ID（用于权限校验）
        data: 盲盒编辑请求数据
        db: 数据库会话

    Returns:
        更新后的 MysteryBox ORM 对象

    Raises:
        ValueError: 盲盒不存在 或 无权修改
    """
    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if not box:
        raise ValueError("盲盒不存在")
    if box.merchant_id != merchant_id:
        raise ValueError("无权修改该盲盒")

    # 仅更新传入的非空字段
    update_data = data.model_dump(exclude_unset=True)

    # 字段名映射：schema 字段名 -> 模型字段名
    field_mapping = {
        "title": "title",
        "description": "description",
        "cover_image": "cover_image",
        "box_type": "box_type",
        "original_price": "original_price",
        "sale_price": "sale_price",
        "stock": "stock",
        "pickup_start_time": "pick_up_start",
        "pickup_end_time": "pick_up_end",
        "status": "status",
    }

    for schema_field, model_field in field_mapping.items():
        if schema_field in update_data:
            value = update_data[schema_field]
            if isinstance(value, Decimal):
                value = float(value)
            setattr(box, model_field, value)

    # 处理标签更新
    if "tags" in update_data and update_data["tags"] is not None:
        # 先删除原有标签
        db.query(BoxTag).filter(BoxTag.box_id == box.id).delete()
        # 再创建新标签
        for tag_name in update_data["tags"]:
            if not tag_name or not tag_name.strip():
                continue
            tag_name = tag_name.strip()
            db.add(BoxTag(box_id=box.id, tag_name=tag_name))

    db.commit()
    db.refresh(box)
    return box


# ──────────────────────────── 盲盒删除（软删除） ────────────────────────────


def delete_box(box_id: int, merchant_id: int, db: Session) -> bool:
    """
    下架盲盒（软删除，将 status 设为 0）。

    Args:
        box_id: 盲盒ID
        merchant_id: 商家ID（用于权限校验）
        db: 数据库会话

    Returns:
        True 表示下架成功

    Raises:
        ValueError: 盲盒不存在 或 无权操作
    """
    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if not box:
        raise ValueError("盲盒不存在")
    if box.merchant_id != merchant_id:
        raise ValueError("无权操作该盲盒")

    box.status = 0
    db.commit()
    return True


# ──────────────────────────── 盲盒详情 ────────────────────────────


def get_box_detail(
    box_id: int,
    db: Session,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> Optional[dict]:
    """
    获取盲盒详情，包含商家名称、标签列表，可选计算距离。

    Args:
        box_id: 盲盒ID
        db: 数据库会话
        lat: 用户纬度（可选，用于计算距离）
        lng: 用户经度（可选，用于计算距离）

    Returns:
        盲盒详情字典，不存在时返回 None
    """
    box = db.query(MysteryBox).filter(MysteryBox.id == box_id).first()
    if not box:
        return None

    # 获取商家信息
    merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()

    # 获取标签列表
    tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()

    # 构建标签响应列表
    tag_list = [{"id": t.id, "tag_name": t.tag_name} for t in tags]

    # 计算距离
    distance = None
    if lat is not None and lng is not None and merchant and merchant.latitude and merchant.longitude:
        distance = haversine_distance(lat, lng, float(merchant.latitude), float(merchant.longitude))

    return {
        "id": box.id,
        "merchant_id": box.merchant_id,
        "title": box.title,
        "description": box.description,
        "cover_image": box.cover_image,
        "box_type": box.box_type,
        "original_price": box.original_price,
        "sale_price": box.sale_price,
        "stock": box.stock,
        "total_stock": box.total_stock,
        "status": box.status,
        "rarity": box.rarity,
        "meme_tags": box.meme_tags,
        "is_revealed": box.is_revealed,
        "pick_up_start": box.pick_up_start,
        "pick_up_end": box.pick_up_end,
        "publish_at": box.publish_at,
        "expired_at": box.expired_at,
        "view_count": box.view_count,
        "sale_count": box.sale_count,
        "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
        "store_name": merchant.store_name if merchant else None,
        "merchant_name": merchant.store_name if merchant else None,
        "store_logo": merchant.logo_url if merchant else None,
        "tags": tag_list,
        "distance": distance,
        "group_min_size": box.group_min_size,
        "group_max_size": box.group_max_size,
        "group_deadline": box.group_deadline,
        "created_at": box.created_at,
        "updated_at": box.updated_at,
    }


# ──────────────────────────── 盲盒列表（筛选 + 排序 + 分页） ────────────────────────────


def get_box_list(query: BoxListQuery, db: Session) -> tuple:
    """
    盲盒列表查询，支持类型筛选、价格区间、标签筛选、距离排序、分页。

    Args:
        query: BoxListQuery 查询参数对象
        db: 数据库会话

    Returns:
        (items: list[dict], total: int) 当前页数据列表 和 总记录数
    """
    # 基础查询：仅查询上架状态的盲盒
    q = db.query(MysteryBox).filter(MysteryBox.status == 1)

    # 类型筛选
    if query.box_type:
        q = q.filter(MysteryBox.box_type == query.box_type)

    # 关键词搜索（标题+描述）
    if query.keyword:
        keyword_pattern = f"%{query.keyword}%"
        q = q.filter(
            (MysteryBox.title.like(keyword_pattern)) |
            (MysteryBox.description.like(keyword_pattern))
        )

    # 价格区间筛选
    if query.min_price is not None:
        q = q.filter(MysteryBox.sale_price >= float(query.min_price))
    if query.max_price is not None:
        q = q.filter(MysteryBox.sale_price <= float(query.max_price))

    # 标签筛选：需要 JOIN BoxTag 表
    if query.tag:
        q = q.join(BoxTag, MysteryBox.id == BoxTag.box_id).filter(
            BoxTag.tag_name == query.tag
        ).distinct()

    # 获取总数
    total = q.count()

    # 排序
    sort_field = query.sort or "default"
    if sort_field == "price_asc":
        q = q.order_by(asc(MysteryBox.sale_price))
    elif sort_field == "price_desc":
        q = q.order_by(desc(MysteryBox.sale_price))
    elif sort_field == "rating":
        q = q.order_by(desc(MysteryBox.rating_avg))
    elif sort_field == "sales":
        q = q.order_by(desc(MysteryBox.sale_count))
    elif sort_field == "default":
        q = q.order_by(desc(MysteryBox.publish_at))
    # distance 排序在 Python 层面处理

    # 分页
    offset = (query.page - 1) * query.size
    boxes = q.offset(offset).limit(query.size).all()

    # 构建结果列表
    items = []
    for box in boxes:
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()

        # 计算距离（当有坐标时）
        distance = None
        if query.lat is not None and query.lng is not None and merchant and merchant.latitude and merchant.longitude:
            distance = haversine_distance(
                query.lat, query.lng,
                float(merchant.latitude), float(merchant.longitude),
            )
            # 如果有半径限制，过滤超出范围的
            if query.radius is not None and distance > query.radius:
                continue

        items.append({
            "id": box.id,
            "merchant_id": box.merchant_id,
            "title": box.title,
            "description": box.description,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
            "original_price": box.original_price,
            "sale_price": box.sale_price,
            "stock": box.stock,
            "status": box.status,
            "sold_count": box.sale_count,
            "rarity": box.rarity,
            "meme_tags": box.meme_tags,
            "is_revealed": box.is_revealed,
            "pickup_start_time": box.pick_up_start,
            "pickup_end_time": box.pick_up_end,
            "store_name": merchant.store_name if merchant else None,
            "merchant_name": merchant.store_name if merchant else None,
            "store_logo": merchant.logo_url if merchant else None,
            "tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags],
            "distance": distance,
            "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
            "created_at": box.created_at,
        })

    # 按距离排序（在 Python 层面）
    if query.sort == "distance" and query.lat is not None and query.lng is not None:
        items.sort(key=lambda x: x.get("distance") if x.get("distance") is not None else float("inf"))

    # 距离排序时，重新计算分页（因为在 Python 层过滤/排序后 total 可能变化）
    if query.sort == "distance" or query.radius is not None:
        # 重新统计总数（应用距离过滤后）
        total = len(items)
        # 重新分页
        start = (query.page - 1) * query.size
        end = start + query.size
        items = items[start:end]

    return items, total


# ──────────────────────────── 附近盲盒 ────────────────────────────


def get_nearby_boxes(
    lat: float,
    lng: float,
    radius: int,
    db: Session,
    box_type: Optional[str] = None,
    limit: int = 20,
) -> list:
    """
    获取指定坐标附近指定半径内的盲盒，按距离由近到远排序。

    Args:
        lat: 用户纬度
        lng: 用户经度
        radius: 搜索半径（米）
        db: 数据库会话
        box_type: 盲盒类型筛选（可选）
        limit: 返回数量上限

    Returns:
        按距离排序的盲盒列表
    """
    # 查询所有上架盲盒
    q = db.query(MysteryBox).filter(MysteryBox.status == 1)
    if box_type:
        q = q.filter(MysteryBox.box_type == box_type)

    boxes = q.all()

    results = []
    for box in boxes:
        # 获取商家坐标
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        if not merchant or not merchant.latitude or not merchant.longitude:
            continue

        distance = haversine_distance(lat, lng, float(merchant.latitude), float(merchant.longitude))
        if distance > radius:
            continue

        tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()

        results.append({
            "id": box.id,
            "merchant_id": box.merchant_id,
            "title": box.title,
            "description": box.description,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
            "original_price": box.original_price,
            "sale_price": box.sale_price,
            "stock": box.stock,
            "status": box.status,
            "sold_count": box.sale_count,
            "rarity": box.rarity,
            "meme_tags": box.meme_tags,
            "is_revealed": box.is_revealed,
            "pickup_start_time": box.pick_up_start,
            "pickup_end_time": box.pick_up_end,
            "store_name": merchant.store_name,
            "store_logo": merchant.logo_url,
            "tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags],
            "distance": distance,
            "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
            "created_at": box.created_at,
        })

    # 按距离升序排列
    results.sort(key=lambda x: x["distance"])
    return results[:limit]


# ──────────────────────────── 商家盲盒列表 ────────────────────────────


def get_merchant_boxes(merchant_id: int, db: Session) -> list:
    """
    获取指定商家的所有盲盒列表（含已下架的）。

    Args:
        merchant_id: 商家ID
        db: 数据库会话

    Returns:
        盲盒列表
    """
    boxes = (
        db.query(MysteryBox)
        .filter(MysteryBox.merchant_id == merchant_id)
        .order_by(desc(MysteryBox.created_at))
        .all()
    )

    results = []
    for box in boxes:
        tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()
        results.append({
            "id": box.id,
            "merchant_id": box.merchant_id,
            "title": box.title,
            "description": box.description,
            "cover_image": box.cover_image,
            "box_type": box.box_type,
            "original_price": box.original_price,
            "sale_price": box.sale_price,
            "stock": box.stock,
            "total_stock": box.total_stock,
            "status": box.status,
            "sold_count": box.sale_count,
            "view_count": box.view_count,
            "rarity": box.rarity,
            "meme_tags": box.meme_tags,
            "is_revealed": box.is_revealed,
            "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
            "tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags],
            "pick_up_start": box.pick_up_start,
            "pick_up_end": box.pick_up_end,
            "publish_at": box.publish_at,
            "created_at": box.created_at,
        })

    return results


# ──────────────────────────── 增加浏览次数 ────────────────────────────


def increment_view_count(box_id: int, db: Session) -> None:
    """
    增加盲盒的浏览次数（+1）。

    Args:
        box_id: 盲盒ID
        db: 数据库会话
    """
    db.query(MysteryBox).filter(MysteryBox.id == box_id).update(
        {MysteryBox.view_count: MysteryBox.view_count + 1},
        synchronize_session=False,
    )
    db.commit()
