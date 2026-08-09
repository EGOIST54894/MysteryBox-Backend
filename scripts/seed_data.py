"""
种子数据脚本 —— 初始化外卖盲盒项目演示数据

运行方式:
    cd backend && python scripts/seed_data.py

演示账号：
- 用户: 13600000000 / 123456
- 商家: 13800000000 / 123456 (湖文美食)
- 配送员: 13900000000 / 123456
"""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Admin,
    Base,
    BoxTag,
    CommunityPost,
    DeliveryOrder,
    DeliveryPersonnel,
    DrawRecord,
    GroupBuyGroup,
    Merchant,
    MysteryBox,
    Order,
    PaymentRecord,
    PostComment,
    PostLike,
    Review,
    User,
    UserAddress,
    UserPreference,
)
from app.models.base import engine, SessionLocal
from app.utils.security import hash_password


# ==================== 演示账号配置 ====================
DEMO_USER_PHONE = "13600000000"
DEMO_USER_PWD = "123456"
DEMO_MERCHANT_PHONE = "13800000000"
DEMO_MERCHANT_PWD = "123456"
DEMO_DELIVERY_PHONE = "13900000000"
DEMO_DELIVERY_PWD = "123456"

SZ_LAT_MIN, SZ_LAT_MAX = 22.52, 22.55
SZ_LNG_MIN, SZ_LNG_MAX = 113.93, 113.96
GZ_LAT_MIN, GZ_LAT_MAX = 23.12, 23.15
GZ_LNG_MIN, GZ_LNG_MAX = 113.32, 113.35
BJ_LAT_MIN, BJ_LAT_MAX = 39.92, 39.98
BJ_LNG_MIN, BJ_LNG_MAX = 116.45, 116.48


def rand_sz_pos():
    """深圳南山区随机坐标"""
    return random.uniform(SZ_LAT_MIN, SZ_LAT_MAX), random.uniform(SZ_LNG_MIN, SZ_LNG_MAX)


# ==================== 15个盲盒数据 ====================
# (标题, 类型, 原价, 售价, 折扣率%, 标签, 库存, 稀有度, 描述)
# 稀有度由折扣率决定: SSR ≥80%, SR ≥55%, R ≥35%, N <35%
BOXES = [
    # ═══ SSR ×2: 超高折扣 ≥80% ═══
    ("至尊海鲜盛宴", "surprise", 78.0, 11.8, 85, ["海鲜", "粤菜", "日料"], 3, "ssr",
     "龙虾、鲍鱼、三文鱼等高端海鲜盲盒，原价78元"),
    ("和牛烤肉拼盘", "surprise", 82.0, 13.9, 83, ["日料", "烧烤", "韩料"], 3, "ssr",
     "A5和牛、黑毛猪、秘制酱料，原价82元"),

    # ═══ SR ×4: 高折扣 ≥55% ═══
    ("川味火锅盛宴", "surprise", 58.0, 17.9, 69, ["川菜", "火锅", "麻辣"], 4, "sr",
     "牛油锅底、毛肚、鸭肠、嫩牛肉，原价58元"),
    ("京城烤鸭套装", "group_buy", 62.0, 21.9, 65, ["中餐", "粤菜", "烧烤"], 6, "sr",
     "整只北京烤鸭+饼皮+配菜，2人起拼，原价62元"),
    ("日料刺身拼盘", "surprise", 68.0, 25.9, 62, ["日料", "海鲜", "清淡"], 4, "sr",
     "三文鱼、金枪鱼、北极贝刺身拼盘，原价68元"),
    ("地道德州牛排", "group_buy", 55.0, 22.9, 58, ["西餐", "烧烤"], 5, "sr",
     "澳洲安格斯牛排300g+薯条+沙拉，2人起拼，原价55元"),

    # ═══ R ×5: 中折扣 ≥35% ═══
    ("麻辣香锅盲盒", "surplus", 45.0, 19.9, 56, ["川菜", "麻辣", "夜宵"], 5, "r",
     "随机搭配肉类+蔬菜+秘制底料，原价45元"),
    ("粤式茶点套餐", "surplus", 42.0, 23.9, 43, ["粤菜", "清淡", "中餐"], 6, "r",
     "虾饺、烧卖、凤爪、叉烧包随机组合，原价42元"),
    ("韩式炸鸡啤酒", "group_buy", 38.0, 20.9, 45, ["韩料", "夜宵", "快餐"], 6, "r",
     "原味/甜辣炸鸡+年糕+饮料，2人起拼，原价38元"),
    ("轻食沙拉碗", "surplus", 36.0, 18.9, 47, ["轻食", "低卡", "素食"], 5, "r",
     "鸡胸肉/三文鱼+藜麦+时蔬+酱汁，原价36元"),
    ("甜品下午茶", "surplus", 40.0, 22.9, 43, ["甜品", "饮品", "素食"], 5, "r",
     "提拉米苏/慕斯蛋糕+饮品+马卡龙，原价40元"),

    # ═══ N ×4: 日常折扣 <35% ═══
    ("打工人的午餐", "surplus", 28.0, 20.9, 25, ["中餐", "快餐", "清淡"], 8, "n",
     "随机盖浇饭/炒面/汤粉套餐，原价28元"),
    ("深夜食堂盲盒", "surplus", 25.0, 18.9, 24, ["夜宵", "烧烤", "麻辣"], 8, "n",
     "随机烧烤/卤味/炒粉套餐，夜猫子必备，原价25元"),
    ("健康轻食便当", "surplus", 22.0, 15.9, 28, ["轻食", "低卡", "素食"], 8, "n",
     "全谷物饭+蔬菜+低脂蛋白质，原价22元"),
    ("快乐碳水盲盒", "surplus", 20.0, 15.9, 21, ["快餐", "中餐", "甜品"], 10, "n",
     "披萨/汉堡/炒饭/蛋糕随机搭配，原价20元"),
]


def seed(db: Session) -> None:
    print("=" * 60)
    print("  外卖盲盒 - 种子数据初始化")
    print("=" * 60)
    print(f"  数据库: {settings.DATABASE_URL}")
    print()

    # ==================== 1. 清空现有数据 ====================
    print("[1/8] 清空现有数据...")
    tables_in_order = [
        PaymentRecord, Review, DeliveryOrder, BoxTag,
        UserPreference, GroupBuyGroup, PostLike, PostComment,
        CommunityPost, DrawRecord, Order, MysteryBox,
        UserAddress, User, Merchant, DeliveryPersonnel, Admin,
    ]
    for table in tables_in_order:
        db.execute(table.__table__.delete())
    db.commit()
    print("    已清空所有表数据。")

    # ==================== 2. 管理员 ====================
    print("[2/8] 创建管理员账号...")
    admin = Admin(
        username="admin",
        password_hash=hash_password("admin123"),
        role="admin",
        status=1,
    )
    db.add(admin)
    db.commit()
    print("    管理员: admin / admin123")

    # ==================== 3. 商家：湖文美食 ====================
    print("[3/8] 创建商家：湖文美食...")
    lat, lng = rand_sz_pos()
    merchant = Merchant(
        phone=DEMO_MERCHANT_PHONE,
        password_hash=hash_password(DEMO_MERCHANT_PWD),
        store_name="湖文美食",
        nickname="湖文美食",
        category="综合美食",
        description="湖文美食城 — 汇聚天下美食，中餐、日料、川菜、粤菜、甜点一应俱全。每天为您准备新鲜美味的盲盒惊喜！",
        logo_url="https://picsum.photos/seed/huwen/200/200",
        status=1,
        latitude=lat, longitude=lng,
        province="广东省", city="深圳市", district="南山区",
        address_detail="粤海街道科技园南路88号湖文美食城1层",
        business_hours='{"open":"09:00","close":"22:00"}',
        rating_avg=4.6,
    )
    db.add(merchant)
    db.flush()
    print(f"    商家: {merchant.store_name} (手机: {DEMO_MERCHANT_PHONE}, 密码: {DEMO_MERCHANT_PWD})")

    # ==================== 4. 配送员 ====================
    print("[4/8] 创建配送员...")
    dp_lat, dp_lng = rand_sz_pos()
    delivery_person = DeliveryPersonnel(
        phone=DEMO_DELIVERY_PHONE,
        password_hash=hash_password(DEMO_DELIVERY_PWD),
        real_name="张师傅",
        nickname="骑手张师傅",
        id_card="440301199001010011",
        status=1,
        current_lat=dp_lat, current_lng=dp_lng,
        rating_avg=4.8,
        completed_orders=365,
    )
    db.add(delivery_person)
    db.flush()
    print(f"    配送员: {delivery_person.real_name} (手机: {DEMO_DELIVERY_PHONE}, 密码: {DEMO_DELIVERY_PWD})")

    # ==================== 5. 用户 ====================
    print("[5/8] 创建演示用户...")
    user = User(
        phone=DEMO_USER_PHONE,
        nickname="测试用户",
        avatar_url="https://picsum.photos/seed/avatar_user/200/200",
        password_hash=hash_password(DEMO_USER_PWD),
        gender=1,
        status=1,
    )
    db.add(user)
    db.flush()

    u_lat, u_lng = rand_sz_pos()
    address = UserAddress(
        user_id=user.id,
        contact_name="测试用户",
        contact_phone=DEMO_USER_PHONE,
        province="广东省", city="深圳市", district="南山区",
        detail="科技园南区A栋1501室",
        latitude=u_lat, longitude=u_lng,
        is_default=True,
    )
    db.add(address)
    db.commit()
    print(f"    用户: {user.nickname} (手机: {DEMO_USER_PHONE}, 密码: {DEMO_USER_PWD})")

    # ==================== 6. 盲盒与标签 ====================
    print("[6/8] 创建15个盲盒...")
    boxes = []
    all_tags = set()

    for i, bdata in enumerate(BOXES):
        title, box_type, orig_price, sale_price, discount, tags, stock, rarity, desc = bdata

        # 拼团设置
        group_min = 2 if box_type == "group_buy" else 0
        group_max = random.randint(3, 5) if box_type == "group_buy" else 0
        group_deadline = datetime.now(timezone.utc) + timedelta(hours=random.randint(24, 72)) if box_type == "group_buy" else None

        # 取餐时间范围
        pick_up_start = datetime.now(timezone.utc) + timedelta(hours=1)
        pick_up_end = datetime.now(timezone.utc) + timedelta(hours=48)

        box = MysteryBox(
            merchant_id=merchant.id,
            title=title,
            description=desc,
            cover_image=f"https://picsum.photos/seed/box_{i}/400/300",
            box_type=box_type,
            original_price=orig_price,
            sale_price=sale_price,
            stock=stock,
            total_stock=stock,
            group_min_size=group_min,
            group_max_size=group_max,
            group_deadline=group_deadline,
            status=1,
            rarity=rarity,
            meme_tags="yyds,绝绝子,真香警告",
            is_revealed=False,
            pick_up_start=pick_up_start,
            pick_up_end=pick_up_end,
            publish_at=datetime.now(timezone.utc),
            expired_at=datetime.now(timezone.utc) + timedelta(hours=random.randint(48, 168)),
            view_count=random.randint(100, 800),
            sale_count=random.randint(0, stock),
            rating_avg=round(random.uniform(3.8, 5.0), 1),
        )
        db.add(box)
        db.flush()
        boxes.append(box)

        for tag_name in tags:
            all_tags.add(tag_name)
            db.add(BoxTag(box_id=box.id, tag_name=tag_name))

    db.commit()
    print(f"    已创建 {len(boxes)} 个盲盒, 标签: {', '.join(sorted(all_tags))}")

    # ==================== 7. 订单（不同状态，便于演示） ====================
    print("[7/8] 创建演示订单...")
    orders_created = 0
    now = datetime.now(timezone.utc)

    # 创建一个 paid（已支付，待配送员接单）的订单
    box1 = boxes[2]  # SR川味火锅
    order_paid = Order(
        order_no="MB20240801001",
        user_id=user.id, box_id=box1.id, address_id=address.id,
        quantity=1, unit_price=float(box1.sale_price),
        total_amount=float(box1.sale_price), discount_amount=0.0,
        paid_amount=float(box1.sale_price),
        order_status="paid",
        paid_at=now - timedelta(minutes=5),
    )
    order_paid.created_at = now - timedelta(minutes=6)
    order_paid.updated_at = now - timedelta(minutes=5)
    db.add(order_paid)
    db.flush()

    # 支付记录
    db.add(PaymentRecord(
        order_id=order_paid.id, transaction_no="PAY10001",
        pay_method="mock", pay_amount=float(box1.sale_price),
        status="success", paid_at=now - timedelta(minutes=5),
    ))
    orders_created += 1

    # 创建一个已确认（配送员已接单，待出餐）的订单
    box2 = boxes[0]  # SSR海鲜
    order_confirmed = Order(
        order_no="MB20240801002",
        user_id=user.id, box_id=box2.id, address_id=address.id,
        quantity=1, unit_price=float(box2.sale_price),
        total_amount=float(box2.sale_price), discount_amount=0.0,
        paid_amount=float(box2.sale_price),
        order_status="confirmed",
        paid_at=now - timedelta(hours=1),
        confirmed_at=now - timedelta(minutes=30),
    )
    order_confirmed.created_at = now - timedelta(hours=1, minutes=1)
    order_confirmed.updated_at = now - timedelta(minutes=30)
    db.add(order_confirmed)
    db.flush()
    db.add(DeliveryOrder(
        order_id=order_confirmed.id, delivery_person_id=delivery_person.id,
        status="assigned", assigned_at=now - timedelta(minutes=30),
    ))
    db.add(PaymentRecord(
        order_id=order_confirmed.id, transaction_no="PAY10002",
        pay_method="mock", pay_amount=float(box2.sale_price),
        status="success", paid_at=now - timedelta(hours=1),
    ))
    orders_created += 1

    # 创建一个待取餐（商家已出餐）的订单
    box3 = boxes[3]  # SR烤鸭
    order_ready = Order(
        order_no="MB20240801003",
        user_id=user.id, box_id=box3.id, address_id=address.id,
        quantity=1, unit_price=float(box3.sale_price),
        total_amount=float(box3.sale_price), discount_amount=0.0,
        paid_amount=float(box3.sale_price),
        order_status="ready_pickup",
        paid_at=now - timedelta(hours=3),
        confirmed_at=now - timedelta(hours=2),
    )
    order_ready.created_at = now - timedelta(hours=3, minutes=1)
    order_ready.updated_at = now - timedelta(minutes=15)
    db.add(order_ready)
    db.flush()
    db.add(DeliveryOrder(
        order_id=order_ready.id, delivery_person_id=delivery_person.id,
        status="assigned", assigned_at=now - timedelta(hours=2),
    ))
    db.add(PaymentRecord(
        order_id=order_ready.id, transaction_no="PAY10003",
        pay_method="mock", pay_amount=float(box3.sale_price),
        status="success", paid_at=now - timedelta(hours=3),
    ))
    orders_created += 1

    # 创建一个已送达的订单
    box4 = boxes[6]  # R麻辣香锅
    order_delivered = Order(
        order_no="MB20240801004",
        user_id=user.id, box_id=box4.id, address_id=address.id,
        quantity=1, unit_price=float(box4.sale_price),
        total_amount=float(box4.sale_price), discount_amount=0.0,
        paid_amount=float(box4.sale_price),
        order_status="delivered",
        paid_at=now - timedelta(hours=5),
        confirmed_at=now - timedelta(hours=4),
        delivered_at=now - timedelta(minutes=10),
    )
    order_delivered.created_at = now - timedelta(hours=5, minutes=1)
    order_delivered.updated_at = now - timedelta(minutes=10)
    db.add(order_delivered)
    db.flush()
    db.add(DeliveryOrder(
        order_id=order_delivered.id, delivery_person_id=delivery_person.id,
        status="delivered",
        assigned_at=now - timedelta(hours=4),
        picked_up_at=now - timedelta(minutes=30),
        delivered_at=now - timedelta(minutes=10),
    ))
    db.add(PaymentRecord(
        order_id=order_delivered.id, transaction_no="PAY10004",
        pay_method="wechat_pay", pay_amount=float(box4.sale_price),
        status="success", paid_at=now - timedelta(hours=5),
    ))
    orders_created += 1

    # 创建一个已完成的订单（带评价）
    box5 = boxes[10]  # N打工人午餐
    order_completed = Order(
        order_no="MB20240801005",
        user_id=user.id, box_id=box5.id, address_id=address.id,
        quantity=2, unit_price=float(box5.sale_price),
        total_amount=float(box5.sale_price) * 2, discount_amount=3.0,
        paid_amount=float(box5.sale_price) * 2 - 3.0,
        order_status="completed",
        paid_at=now - timedelta(days=1),
        confirmed_at=now - timedelta(days=1, hours=2),
        delivered_at=now - timedelta(days=1, hours=3),
        completed_at=now - timedelta(days=1, hours=4),
    )
    order_completed.created_at = now - timedelta(days=1, minutes=1)
    order_completed.updated_at = now - timedelta(days=1, hours=4)
    db.add(order_completed)
    db.flush()
    db.add(DeliveryOrder(
        order_id=order_completed.id, delivery_person_id=delivery_person.id,
        status="delivered",
        assigned_at=now - timedelta(days=1, hours=1),
        picked_up_at=now - timedelta(days=1, hours=2, minutes=30),
        delivered_at=now - timedelta(days=1, hours=3),
    ))
    db.add(PaymentRecord(
        order_id=order_completed.id, transaction_no="PAY10005",
        pay_method="alipay", pay_amount=float(box5.sale_price) * 2 - 3.0,
        status="success", paid_at=now - timedelta(days=1),
    ))
    orders_created += 1

    # 已完成订单的评价
    db.add(Review(
        order_id=order_completed.id, user_id=user.id, box_id=box5.id,
        rating=4, content="盲盒体验很好！开出了一份红烧牛肉饭+冰红茶，分量足味道也不错。打工人午餐性价比很高，会继续回购！",
        images="[\"https://picsum.photos/seed/review1/400/400\"]",
        is_anonymous=False, status=1,
    ))

    db.commit()
    print(f"    已创建 {orders_created} 个演示订单（覆盖 paid/confirmed/ready_pickup/delivered/completed 状态）")

    # ==================== 8. 抽卡记录 ====================
    print("[8/8] 创建抽卡记录...")
    for i in range(min(5, len(boxes))):
        box = boxes[i]
        dr = DrawRecord(
            user_id=user.id, box_id=box.id,
            rarity=box.rarity or "n",
            draw_price=float(box.sale_price),
            status="ordered" if i < 3 else "pending",
            draw_count=i + 1,
        )
        dr.created_at = now - timedelta(hours=random.randint(1, 48))
        dr.updated_at = dr.created_at
        db.add(dr)
    db.commit()
    print(f"    已创建 5 条抽卡记录。")

    # ==================== 汇总 ====================
    print()
    print("=" * 60)
    print("  种子数据初始化完成!")
    print("=" * 60)
    print(f"  管理员:   admin / admin123")
    print(f"  用户:     {DEMO_USER_PHONE} / {DEMO_USER_PWD} (昵称: 测试用户)")
    print(f"  商家:     {DEMO_MERCHANT_PHONE} / {DEMO_MERCHANT_PWD} (湖文美食)")
    print(f"  配送员:   {DEMO_DELIVERY_PHONE} / {DEMO_DELIVERY_PWD} (张师傅)")
    print(f"  盲盒:     {len(boxes)} 个")
    print(f"  订单:     {orders_created} 个")
    print()
    print("  准备就绪，可以启动项目了!")
    print("=" * 60)


def main():
    print("创建/验证数据库表...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed(db)
    except Exception as e:
        db.rollback()
        print(f"\n[错误] 种子数据初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
