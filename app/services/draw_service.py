"""外卖盲盒 - 抽卡系统业务逻辑层

提供抽卡核心算法、用户抽卡统计、抽卡历史等功能。
抽卡流程: 按稀有度概率随机 -> 从对应稀有度池中选盲盒 -> 创建抽卡记录。
"""

import random
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.draw import DrawRecord
from app.models.merchant import Merchant
from app.models.mystery_box import BoxTag, MysteryBox

# 稀有度概率配置（累积概率）
RARITY_PROBABILITIES = [
    ("ssr", 0.10),   # 10%
    ("sr", 0.25),    # 15% (10%+15%)
    ("r", 0.45),     # 20% (25%+20%)
    ("n", 1.00),     # 55% (45%+55%)
]

# 稀有度降级顺序
RARITY_ORDER = ["ssr", "sr", "r", "n"]

# 每日免费抽卡次数上限
DAILY_FREE_DRAW_LIMIT = 3

# 抽中稀有度的随机梗文案
RARITY_MEME_MAP = {
    "ssr": [
        "金色传说！🎉 欧皇降临！",
        "这波血赚！SSR！",
        "天选之人就是你！金光闪闪！",
        "欧气爆棚！传说中的SSR！",
    ],
    "sr": [
        "欧气满满！SR到手！",
        "不错的收获！",
        "紫气东来，好运连连！",
        "SR品质，相当不亏！",
    ],
    "r": [
        "还行还行，R级美味",
        "日常小确幸~",
        "小有惊喜，R级也不错！",
        "稳妥之选，R级到手！",
    ],
    "n": [
        "平平淡淡才是真",
        "性价比之选！",
        "日常美味，朴实无华",
        "基础款也有大快乐！",
    ],
}

# 稀有度中文名
RARITY_NAME_MAP = {
    "ssr": "SSR·传说",
    "sr": "SR·稀有",
    "r": "R·精良",
    "n": "N·普通",
}

# 根据排名返回头衔
RANK_TITLES = [
    (0, "抽卡新手"),
    (5, "初级猎手"),
    (15, "欧气学徒"),
    (30, "幸运星"),
    (50, "抽卡达人"),
    (100, "欧皇候选人"),
    (200, "欧皇本皇"),
    (500, "盲盒之神"),
]


def _roll_rarity() -> str:
    """按概率随机抽取一个稀有度等级"""
    roll = random.random()
    for rarity, cumulative_prob in RARITY_PROBABILITIES:
        if roll < cumulative_prob:
            return rarity
    return "n"  # 兜底


def _get_rarity_index(rarity: str) -> int:
    """获取稀有度在降级顺序中的索引，用于降级遍历"""
    try:
        return RARITY_ORDER.index(rarity)
    except ValueError:
        return len(RARITY_ORDER) - 1


def _build_box_query(db: Session, rarity: str, filters: dict):
    """构建盲盒查询（按稀有度和筛选条件）"""
    q = db.query(MysteryBox).filter(
        MysteryBox.status == 1,
        MysteryBox.rarity == rarity,
    )

    # 价格筛选（按售价 sale_price 过滤，用户关心实际支付价格）
    if filters.get("min_price") is not None:
        q = q.filter(MysteryBox.sale_price >= float(filters["min_price"]))
    if filters.get("max_price") is not None:
        q = q.filter(MysteryBox.sale_price <= float(filters["max_price"]))

    # 标签筛选（通过 BoxTag 表 JOIN）
    tags = filters.get("tags")
    if tags:
        if isinstance(tags, str):
            tags = [tags]
        q = q.join(BoxTag, MysteryBox.id == BoxTag.box_id).filter(
            BoxTag.tag_name.in_(tags)
        ).distinct()

    # 城市筛选（通过商家表 JOIN）
    city = filters.get("city")
    if city:
        q = q.join(Merchant, MysteryBox.merchant_id == Merchant.id).filter(
            Merchant.city == city
        ).distinct()

    return q


def _get_today_draw_count(user_id: int, db: Session) -> int:
    """获取用户今日已抽卡次数"""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        db.query(func.count(DrawRecord.id))
        .filter(
            DrawRecord.user_id == user_id,
            DrawRecord.created_at >= today,
        )
        .scalar()
    )
    return count or 0


def draw_box(
    user_id: int,
    filters: Optional[dict] = None,
    db: Session = None,
) -> dict:
    """
    执行抽卡。

    算法流程:
    1. 按稀有度概率随机决定本次抽到的稀有度等级
    2. 从该稀有度对应的盲盒池中随机选取一个
    3. 如果该稀有度池为空（无可用盲盒），则自动降级到下一稀有度
    4. 记录抽卡记录到数据库
    5. 返回抽卡结果（不含具体餐品内容，仅含类型标签和梗文案）

    Args:
        user_id: 用户ID
        filters: 可选筛选条件字典 (min_price, max_price, tags, city)
        db: 数据库会话

    Returns:
        包含抽卡结果的字典: box_info, rarity, draw_record_id, meme_text, daily_remaining
    """
    if filters is None:
        filters = {}

    # 确定起始稀有度
    target_rarity = _roll_rarity()
    start_idx = _get_rarity_index(target_rarity)

    selected_box = None
    final_rarity = target_rarity

    # 从目标稀有度开始向下降级查找
    for i in range(start_idx, len(RARITY_ORDER)):
        current_rarity = RARITY_ORDER[i]
        q = _build_box_query(db, current_rarity, filters)
        candidates = q.all()

        if candidates:
            selected_box = random.choice(candidates)
            final_rarity = current_rarity
            break

    if selected_box is None:
        # 所有稀有度都没有匹配的盲盒——放宽稀有度限制再试一次
        q = db.query(MysteryBox).filter(MysteryBox.status == 1)
        if filters.get("min_price") is not None:
            q = q.filter(MysteryBox.sale_price >= float(filters["min_price"]))
        if filters.get("max_price") is not None:
            q = q.filter(MysteryBox.sale_price <= float(filters["max_price"]))
        tags = filters.get("tags")
        if tags:
            if isinstance(tags, str):
                tags = [tags]
            q = q.join(BoxTag, MysteryBox.id == BoxTag.box_id).filter(
                BoxTag.tag_name.in_(tags)
            ).distinct()
        city = filters.get("city")
        if city:
            q = q.join(Merchant, MysteryBox.merchant_id == Merchant.id).filter(
                Merchant.city == city
            ).distinct()

        candidates = q.all()
        if not candidates:
            raise ValueError("当前筛选条件下没有可用的盲盒，请调整筛选条件后重试")

        selected_box = random.choice(candidates)
        final_rarity = selected_box.rarity or "n"

    # 计算今日抽卡序号
    today_draw_count = _get_today_draw_count(user_id, db)
    draw_seq = today_draw_count + 1

    # 获取盲盒标签
    tags = db.query(BoxTag).filter(BoxTag.box_id == selected_box.id).all()
    tag_names = [t.tag_name for t in tags]

    # 获取商家信息
    merchant = db.query(Merchant).filter(Merchant.id == selected_box.merchant_id).first()

    # 创建抽卡记录
    draw_record = DrawRecord(
        user_id=user_id,
        box_id=selected_box.id,
        rarity=final_rarity,
        draw_price=float(selected_box.sale_price),
        status="pending",
        draw_count=draw_seq,
    )
    db.add(draw_record)
    db.commit()
    db.refresh(draw_record)

    # 随机选取一条梗文案
    meme_options = RARITY_MEME_MAP.get(final_rarity, ["未知惊喜！"])
    meme_text = random.choice(meme_options)

    # 计算今日剩余免费次数
    daily_remaining = max(0, DAILY_FREE_DRAW_LIMIT - draw_seq)

    return {
        "draw_record_id": draw_record.id,
        "rarity": final_rarity,
        "rarity_name": RARITY_NAME_MAP.get(final_rarity, final_rarity),
        "meme_text": meme_text,
        "box_info": {
            "id": selected_box.id,
            "box_type": selected_box.box_type,
            "title": selected_box.title,
            "cover_image": selected_box.cover_image,
            "sale_price": float(selected_box.sale_price),
            "original_price": float(selected_box.original_price),
            "description": selected_box.description,
            "meme_tags": selected_box.meme_tags,
            "tags": tag_names,
            "store_name": merchant.store_name if merchant else None,
            "merchant_name": merchant.store_name if merchant else None,
            "city": merchant.city if merchant else None,
        },
        "daily_remaining": daily_remaining,
        "draw_count": draw_seq,
    }


def get_user_draw_stats(user_id: int, db: Session) -> dict:
    """
    获取用户抽卡统计数据。

    Args:
        user_id: 用户ID
        db: 数据库会话

    Returns:
        统计数据字典: total_draws, ssr_count, sr_count, r_count, n_count, luck_value, rank_title
    """
    total_draws = (
        db.query(func.count(DrawRecord.id))
        .filter(DrawRecord.user_id == user_id)
        .scalar()
    ) or 0

    # 各稀有度计数
    rarity_counts = {"ssr": 0, "sr": 0, "r": 0, "n": 0}
    rows = (
        db.query(DrawRecord.rarity, func.count(DrawRecord.id))
        .filter(DrawRecord.user_id == user_id)
        .group_by(DrawRecord.rarity)
        .all()
    )
    for rarity, count in rows:
        if rarity in rarity_counts:
            rarity_counts[rarity] = count

    # 幸运值计算: SSR=50分, SR=20分, R=10分, N=5分（直接累加，不归一化）
    ssr_count = rarity_counts["ssr"]
    sr_count = rarity_counts["sr"]
    r_count = rarity_counts["r"]
    n_count = rarity_counts["n"]

    luck_value = ssr_count * 50 + sr_count * 20 + r_count * 10 + n_count * 5

    # 根据总抽卡次数确定头衔
    rank_title = "抽卡新手"
    for threshold, title in RANK_TITLES:
        if total_draws >= threshold:
            rank_title = title
        else:
            break

    return {
        "total_draws": total_draws,
        "ssr_count": ssr_count,
        "sr_count": sr_count,
        "r_count": r_count,
        "n_count": n_count,
        "luck_value": luck_value,
        "rank_title": rank_title,
        "daily_remaining": max(0, DAILY_FREE_DRAW_LIMIT - _get_today_draw_count(user_id, db)),
    }


def get_draw_history(
    user_id: int,
    page: int = 1,
    size: int = 10,
    db: Session = None,
) -> tuple:
    """
    获取用户抽卡历史列表（分页）。

    Args:
        user_id: 用户ID
        page: 页码（从1开始）
        size: 每页条数
        db: 数据库会话

    Returns:
        (items: list[dict], total: int)
    """
    total = (
        db.query(func.count(DrawRecord.id))
        .filter(DrawRecord.user_id == user_id)
        .scalar()
    ) or 0

    records = (
        db.query(DrawRecord)
        .filter(DrawRecord.user_id == user_id)
        .order_by(DrawRecord.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for dr in records:
        box = dr.mystery_box
        merchant = db.query(Merchant).filter(Merchant.id == box.merchant_id).first()
        tags = db.query(BoxTag).filter(BoxTag.box_id == box.id).all()

        items.append({
            "id": dr.id,
            "box_id": dr.box_id,
            "rarity": dr.rarity,
            "rarity_name": RARITY_NAME_MAP.get(dr.rarity, dr.rarity),
            "draw_price": dr.draw_price,
            "status": dr.status,
            "draw_count": dr.draw_count,
            "box_title": box.title,
            "box_type": box.box_type,
            "cover_image": box.cover_image,
            "meme_tags": box.meme_tags,
            "store_name": merchant.store_name if merchant else None,
            "merchant_name": merchant.store_name if merchant else None,
            "tags": [t.tag_name for t in tags],
            "meme_text": random.choice(RARITY_MEME_MAP.get(dr.rarity, ["惊喜时刻！"])),
            "created_at": dr.created_at.isoformat() if dr.created_at else None,
        })

    return items, total
