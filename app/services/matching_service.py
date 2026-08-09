"""
盲盒推荐匹配算法模块

实现基于用户偏好、距离、评分、热门度、价格匹配五个维度的混合推荐算法。
同时提供用户偏好标签的更新机制（基于浏览、购买、高评分等行为）。
"""

import math
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.merchant import Merchant
from app.models.mystery_box import BoxTag, MysteryBox, UserPreference
from app.models.order import Order
from app.utils.geo import haversine_distance


# ──────────────────────────── 推荐算法 ────────────────────────────


def recommend_boxes(
    user_id: int,
    lat: float,
    lng: float,
    radius: int = 5000,
    limit: int = 20,
    db: Optional[Session] = None,
) -> list:
    """
    混合推荐算法（5维打分）。

    得分 = 标签匹配(30%) + 距离分(25%) + 评分分(20%) + 热门度(15%) + 价格匹配(10%)

    1. 标签匹配: 用户偏好标签 vs 盲盒标签的 Jaccard 相似度
    2. 距离分: 1 - haversine/radius（距离越近分越高）
    3. 评分分: box.rating_avg / 5.0
    4. 热门度: log(1 + sale_count) / log(1 + max_sales)
    5. 价格匹配: 与用户历史均价偏差归一化

    多样性控制: 同一商家最多出现3个盲盒

    Args:
        user_id: 用户ID
        lat: 用户当前纬度
        lng: 用户当前经度
        radius: 搜索半径（米），默认5000
        limit: 返回数量上限，默认20
        db: 数据库会话

    Returns:
        按综合得分降序排列的盲盒推荐列表
    """
    # 1. 获取用户偏好标签及其权重
    user_prefs = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).all()
    user_tag_weights = {p.tag_name: float(p.weight) for p in user_prefs}
    user_tag_set = set(user_tag_weights.keys())

    # 2. 获取用户历史订单均价（用于价格匹配维度）
    user_avg_price_result = db.query(func.avg(Order.unit_price)).filter(
        Order.user_id == user_id,
        Order.order_status.in_(["completed", "paid", "delivering", "delivered", "ready_pickup"]),
    ).scalar()
    user_avg_price = float(user_avg_price_result) if user_avg_price_result else None

    # 3. 获取候选盲盒（上架状态、有库存）
    candidates = (
        db.query(MysteryBox)
        .filter(
            MysteryBox.status == 1,
            MysteryBox.stock > 0,
        )
        .all()
    )

    if not candidates:
        return []

    # 4. 预加载候选盲盒的商家和标签信息
    candidate_data = []
    for box in candidates:
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        if not merchant or not merchant.latitude or not merchant.longitude:
            continue

        # 距离计算
        distance = haversine_distance(lat, lng, float(merchant.latitude), float(merchant.longitude))
        if distance > radius:
            continue

        # 获取盲盒标签
        tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()
        tag_names = [t.tag_name for t in tags]

        candidate_data.append({
            "box": box,
            "merchant": merchant,
            "distance": distance,
            "tag_names": tag_names,
        })

    if not candidate_data:
        return []

    # 5. 计算各维度最大值（用于归一化）
    max_sales = max((d["box"].sale_count for d in candidate_data), default=1)
    max_distance = max((d["distance"] for d in candidate_data), default=1)
    min_distance = min((d["distance"] for d in candidate_data), default=0)
    distance_range = max_distance - min_distance or 1  # 避免除零

    # 收集价格用于价格偏差计算
    prices = [float(d["box"].sale_price) for d in candidate_data]
    price_std = float(
        (sum((p - (sum(prices) / len(prices))) ** 2 for p in prices) / len(prices)) ** 0.5
    ) if prices else 1.0

    # 6. 计算每个候选盲盒的综合得分
    scored = []
    for data in candidate_data:
        box = data["box"]
        merchant = data["merchant"]
        distance = data["distance"]
        tag_names = data["tag_names"]

        # ---- 维度1: 标签匹配得分 (权重30%) ----
        box_tag_set = set(tag_names)
        tag_score = 0.0
        if box_tag_set or user_tag_set:
            # Jaccard 相似度: |A ∩ B| / |A ∪ B|
            intersection = user_tag_set & box_tag_set
            union = user_tag_set | box_tag_set
            jaccard = len(intersection) / len(union) if union else 0.0

            # 加权 Jaccard: 考虑用户偏好权重
            if intersection:
                weighted_sum = sum(user_tag_weights.get(t, 1.0) for t in intersection)
                total_weight = sum(user_tag_weights.get(t, 1.0) for t in union) if union else 1.0
                tag_score = weighted_sum / total_weight
            else:
                tag_score = 0.0

        # ---- 维度2: 距离得分 (权重25%) ----
        # 距离越近分越高：1 - distance/radius，确保在范围内为正值
        distance_score = max(0.0, 1.0 - distance / radius)

        # ---- 维度3: 评分得分 (权重20%) ----
        rating = float(box.rating_avg) if box.rating_avg else 0.0
        rating_score = rating / 5.0

        # ---- 维度4: 热门度得分 (权重15%) ----
        popularity_score = math.log(1 + box.sale_count) / math.log(1 + max_sales) if max_sales > 0 else 0.0

        # ---- 维度5: 价格匹配得分 (权重10%) ----
        price_score = 0.5  # 默认中等分
        if user_avg_price is not None and price_std > 0:
            price_diff = abs(float(box.sale_price) - user_avg_price)
            # 偏差越小分越高: 1 - normalized_diff，裁剪到[0, 1]
            normalized_diff = min(1.0, price_diff / (price_std * 2 + 0.01))
            price_score = 1.0 - normalized_diff

        # ---- 综合得分 ----
        final_score = (
            tag_score * 0.30
            + distance_score * 0.25
            + rating_score * 0.20
            + popularity_score * 0.15
            + price_score * 0.10
        )

        scored.append({
            **data,
            "final_score": final_score,
            "scores_detail": {
                "tag_score": round(tag_score, 4),
                "distance_score": round(distance_score, 4),
                "rating_score": round(rating_score, 4),
                "popularity_score": round(popularity_score, 4),
                "price_score": round(price_score, 4),
                "final_score": round(final_score, 4),
            },
        })

    # 7. 按综合得分降序排列
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # 8. 多样性控制：同一商家最多出现3个盲盒
    merchant_count = {}
    diversified = []
    for item in scored:
        mid = item["box"].merchant_id
        count = merchant_count.get(mid, 0)
        if count >= 3:
            continue
        merchant_count[mid] = count + 1
        diversified.append(item)

    # 9. 构建返回结果
    results = []
    for item in diversified[:limit]:
        box = item["box"]
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
            "pickup_start_time": box.pick_up_start,
            "pickup_end_time": box.pick_up_end,
            "store_name": item["merchant"].store_name,
            "store_logo": item["merchant"].logo_url,
            "tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags],
            "distance": item["distance"],
            "rating_avg": float(box.rating_avg) if box.rating_avg else 0.0,
            "recommend_score": round(item["final_score"], 4),
            "scores_detail": item["scores_detail"],
            "created_at": box.created_at,
        })

    return results


# ──────────────────────────── 用户偏好更新 ────────────────────────────


def update_user_preferences(
    user_id: int,
    box_id: int,
    action_type: str,
    db: Session,
) -> None:
    """
    根据用户行为更新偏好标签权重。

    行为类型及权重增量:
        - 'view': 浏览超过10秒，权重 +0.03
        - 'purchase': 完成购买，权重 +0.10
        - 'high_rating': 评分 >= 4星，权重 +0.05

    Args:
        user_id: 用户ID
        box_id: 盲盒ID
        action_type: 行为类型
        db: 数据库会话
    """
    # 行为权重映射
    action_weights = {
        "view": 0.03,
        "purchase": 0.10,
        "high_rating": 0.05,
    }

    if action_type not in action_weights:
        raise ValueError(f"不支持的行为类型: {action_type}")

    weight_delta = action_weights[action_type]

    # 获取该盲盒的所有标签
    box_tags = db.query(BoxTag).filter(BoxTag.box_id == box_id).all()
    if not box_tags:
        return

    for box_tag in box_tags:
        tag_name = box_tag.tag_name

        # 查找用户是否已有该标签偏好
        user_pref = db.query(UserPreference).filter(
            UserPreference.user_id == user_id,
            UserPreference.tag_name == tag_name,
        ).first()

        if user_pref:
            # 更新已有偏好权重（最大不超过 5.0）
            new_weight = float(user_pref.weight) + weight_delta
            user_pref.weight = min(5.0, new_weight)
        else:
            # 新建偏好记录，初始权重 = 1.0 + 增量
            initial_weight = 1.0 + weight_delta
            user_pref = UserPreference(
                user_id=user_id,
                tag_name=tag_name,
                weight=min(5.0, initial_weight),
            )
            db.add(user_pref)

    db.commit()
