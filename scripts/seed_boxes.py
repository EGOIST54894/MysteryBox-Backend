"""
种子数据脚本 - 湖文美食盲盒
覆盖所有筛选方向：4种稀有度 × 3种类型 × 多种标签 × 多价位
"""
import sys
sys.path.insert(0, ".")

from app.models.base import SessionLocal
from app.models.mystery_box import MysteryBox, BoxTag
from app.models.merchant import Merchant

db = SessionLocal()

# 清空现有盲盒和标签
db.query(BoxTag).delete()
db.query(MysteryBox).delete()
db.commit()

# 湖文美食 - 襄阳
merchant = db.query(Merchant).filter(Merchant.id == 1).first()
if not merchant:
    print("商家不存在!")
    sys.exit(1)

# 24个盲盒：覆盖 4稀有度 × 3类型 × 多标签 × 多价位
boxes = [
    # ======== SSR (4个) ========
    {"title": "湖文至尊盛宴", "box_type": "surprise", "rarity": "ssr",
     "original_price": 198.00, "sale_price": 25.90, "stock": 5,
     "cover_image": "", "description": "隐藏款·顶级日料双人宴",
     "meme_tags": "金色传说/欧皇降临/尊享盛宴",
     "tags": ["日料", "双人餐", "隐藏款"]},

    {"title": "襄阳霸王火锅", "box_type": "group_buy", "rarity": "ssr",
     "original_price": 268.00, "sale_price": 29.90, "stock": 3,
     "cover_image": "", "description": "限量·地道襄阳牛油火锅3人拼",
     "meme_tags": "霸王级/一锅入魂/红油滚滚",
     "tags": ["火锅", "麻辣", "拼单"]},

    {"title": "汉江渔夫全鱼宴", "box_type": "surprise", "rarity": "ssr",
     "original_price": 188.00, "sale_price": 22.90, "stock": 4,
     "cover_image": "", "description": "SSR·汉江鲜鱼十二吃",
     "meme_tags": "鱼跃龙门/鲜掉眉毛/汉江至味",
     "tags": ["清淡", "双人餐", "人气"]},

    {"title": "隆中卧龙烤肉拼盘", "box_type": "surplus", "rarity": "ssr",
     "original_price": 158.00, "sale_price": 19.90, "stock": 6,
     "cover_image": "", "description": "卧龙出山·秘制烤肉盛宴",
     "meme_tags": "卧龙真传/肉食者的天堂/炭火飘香",
     "tags": ["烧烤", "双人餐", "爆款"]},

    # ======== SR (6个) ========
    {"title": "古城秘制牛肉面", "box_type": "surplus", "rarity": "sr",
     "original_price": 68.00, "sale_price": 15.90, "stock": 10,
     "cover_image": "", "description": "襄阳牛肉面·一清二白三红",
     "meme_tags": "古城味道/面中一绝/清晨必嗦",
     "tags": ["快餐", "麻辣", "人气"]},

    {"title": "汉水清蒸鲈鱼", "box_type": "surprise", "rarity": "sr",
     "original_price": 88.00, "sale_price": 18.90, "stock": 8,
     "cover_image": "", "description": "汉江鲜·清蒸鲈鱼套餐",
     "meme_tags": "清淡鲜美/江鲜一绝/养生首选",
     "tags": ["清淡", "双人餐", "低卡"]},

    {"title": "隆中素斋轻食盒", "box_type": "surprise", "rarity": "sr",
     "original_price": 58.00, "sale_price": 14.90, "stock": 12,
     "cover_image": "", "description": "低卡轻食·诸葛亮也爱的素食",
     "meme_tags": "轻食主义/素雅之选/健康低卡",
     "tags": ["低卡", "清淡", "素食"]},

    {"title": "麻辣小龙虾拼团", "box_type": "group_buy", "rarity": "sr",
     "original_price": 128.00, "sale_price": 24.90, "stock": 7,
     "cover_image": "", "description": "襄阳小龙虾·麻辣鲜香2人拼",
     "meme_tags": "虾王争霸/麻辣爽翻天/剥虾快乐",
     "tags": ["火锅", "麻辣", "拼单"]},

    {"title": "古城烧烤大礼包", "box_type": "surplus", "rarity": "sr",
     "original_price": 78.00, "sale_price": 16.90, "stock": 9,
     "cover_image": "", "description": "深夜食堂·襄阳烤串大礼包",
     "meme_tags": "深夜放毒/炭烤飘香/串串精彩",
     "tags": ["烧烤", "夜宵", "实惠"]},

    {"title": "汉江甜品下午茶", "box_type": "surprise", "rarity": "sr",
     "original_price": 48.00, "sale_price": 12.90, "stock": 15,
     "cover_image": "", "description": "精致甜品·下午茶时光",
     "meme_tags": "甜蜜时光/茶香四溢/午后小确幸",
     "tags": ["甜品", "下午茶", "饮品"]},

    # ======== R (8个) ========
    {"title": "襄阳黄酒配卤味", "box_type": "surplus", "rarity": "r",
     "original_price": 42.00, "sale_price": 11.90, "stock": 20,
     "cover_image": "", "description": "襄阳老黄酒·配秘制卤味",
     "meme_tags": "酒香不怕巷子深/卤味绝配/襄阳特色",
     "tags": ["饮品", "快餐", "实惠"]},

    {"title": "古城炒饭便当", "box_type": "surplus", "rarity": "r",
     "original_price": 32.00, "sale_price": 9.90, "stock": 25,
     "cover_image": "", "description": "蛋炒饭·家的味道",
     "meme_tags": "朴实无华/家的味道/粒粒分明",
     "tags": ["快餐", "实惠", "午餐"]},

    {"title": "隆中清茶一壶", "box_type": "surprise", "rarity": "r",
     "original_price": 38.00, "sale_price": 8.90, "stock": 30,
     "cover_image": "", "description": "隆中清茶·闲适时光",
     "meme_tags": "茶香一缕/隆中风雅/清心明目",
     "tags": ["饮品", "清淡", "下午茶"]},

    {"title": "麻辣烫盲盒套餐", "box_type": "surplus", "rarity": "r",
     "original_price": 35.00, "sale_price": 10.90, "stock": 18,
     "cover_image": "", "description": "麻辣烫·随心搭配",
     "meme_tags": "麻辣烫/鲜香热辣/冬日暖身",
     "tags": ["麻辣", "快餐", "实惠"]},

    {"title": "双人奶茶拼团", "box_type": "group_buy", "rarity": "r",
     "original_price": 46.00, "sale_price": 13.90, "stock": 14,
     "cover_image": "", "description": "2人拼·网红奶茶套餐",
     "meme_tags": "奶茶续命/双人甜蜜/快乐水",
     "tags": ["饮品", "拼单", "甜品"]},

    {"title": "襄阳红糖糍粑", "box_type": "surprise", "rarity": "r",
     "original_price": 28.00, "sale_price": 7.90, "stock": 22,
     "cover_image": "", "description": "传统甜品·红糖糍粑",
     "meme_tags": "软糯香甜/古法红糖/儿时味道",
     "tags": ["甜品", "小吃", "人气"]},

    {"title": "轻食沙拉便当", "box_type": "surplus", "rarity": "r",
     "original_price": 36.00, "sale_price": 11.90, "stock": 16,
     "cover_image": "", "description": "低卡沙拉·鸡胸肉便当",
     "meme_tags": "健身达人/低卡首选/清爽一天",
     "tags": ["低卡", "清淡", "午餐"]},

    {"title": "日式寿司小拼", "box_type": "surprise", "rarity": "r",
     "original_price": 45.00, "sale_price": 12.90, "stock": 13,
     "cover_image": "", "description": "日式寿司·小巧精致",
     "meme_tags": "精致日料/一口一个/寿司控",
     "tags": ["日料", "清淡", "人气"]},

    # ======== N (6个) ========
    {"title": "襄阳豆腐面", "box_type": "surplus", "rarity": "n",
     "original_price": 18.00, "sale_price": 5.90, "stock": 40,
     "cover_image": "", "description": "襄阳特色·豆腐面早餐",
     "meme_tags": "平凡中的美味/襄阳人的早餐/一碗入魂",
     "tags": ["快餐", "实惠", "早餐"]},

    {"title": "绿豆汤消暑套餐", "box_type": "surplus", "rarity": "n",
     "original_price": 15.00, "sale_price": 4.90, "stock": 35,
     "cover_image": "", "description": "夏日消暑·冰镇绿豆汤",
     "meme_tags": "消暑利器/清凉一夏/解暑必备",
     "tags": ["饮品", "低卡", "甜品"]},

    {"title": "红糖冰粉碗", "box_type": "surprise", "rarity": "n",
     "original_price": 12.00, "sale_price": 3.90, "stock": 45,
     "cover_image": "", "description": "手工冰粉·红糖花生碎",
     "meme_tags": "夏日必吃/冰凉爽滑/消暑神器",
     "tags": ["甜品", "小吃", "实惠"]},

    {"title": "蛋炒饭基础便当", "box_type": "surplus", "rarity": "n",
     "original_price": 20.00, "sale_price": 6.90, "stock": 50,
     "cover_image": "", "description": "基础款·蛋炒饭便当",
     "meme_tags": "朴实无华/温饱之选/量大管饱",
     "tags": ["快餐", "午餐", "实惠"]},

    {"title": "酸梅汤解辣套装", "box_type": "surprise", "rarity": "n",
     "original_price": 16.00, "sale_price": 4.90, "stock": 38,
     "cover_image": "", "description": "酸梅汤·解辣神器",
     "meme_tags": "解辣必备/冰镇更好喝/火锅伴侣",
     "tags": ["饮品", "低卡", "实惠"]},

    {"title": "小笼包早餐盲盒", "box_type": "surplus", "rarity": "n",
     "original_price": 22.00, "sale_price": 7.90, "stock": 30,
     "cover_image": "", "description": "小笼包·鲜肉灌汤",
     "meme_tags": "灌汤流油/一笼不够/早餐首选",
     "tags": ["快餐", "早餐", "人气"]},
]

for box_data in boxes:
    tags = box_data.pop("tags")
    box = MysteryBox(
        merchant_id=merchant.id,
        status=1,  # 上架
        **box_data
    )
    db.add(box)
    db.flush()

    # 添加标签
    for tag_name in tags:
        tag = BoxTag(box_id=box.id, tag_name=tag_name)
        db.add(tag)

db.commit()
print(f"✅ 成功创建 {len(boxes)} 个盲盒，来自 {merchant.store_name}（{merchant.city}）")

# 验证
count = db.query(MysteryBox).count()
tag_count = db.query(BoxTag).count()
print(f"   盲盒总数: {count}")
print(f"   标签总数: {tag_count}")

# 稀有度分布
from sqlalchemy import func
for rarity in ["ssr", "sr", "r", "n"]:
    c = db.query(func.count(MysteryBox.id)).filter(MysteryBox.rarity == rarity).scalar()
    print(f"   {rarity}: {c}个")

# 类型分布
for bt in ["surprise", "surplus", "group_buy"]:
    c = db.query(func.count(MysteryBox.id)).filter(MysteryBox.box_type == bt).scalar()
    print(f"   {bt}: {c}个")

# 价格范围
price_range = db.query(func.min(MysteryBox.sale_price), func.max(MysteryBox.sale_price),
                        func.min(MysteryBox.original_price), func.max(MysteryBox.original_price)).first()
print(f"   售价范围: ¥{price_range[0]} ~ ¥{price_range[1]}")
print(f"   原价范围: ¥{price_range[2]} ~ ¥{price_range[3]}")

db.close()
