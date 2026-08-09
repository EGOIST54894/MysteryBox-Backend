"""Service层集成测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.config import settings

# 使用 SQLite 内存数据库
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine)


@pytest.fixture(scope="function")
def db():
    """每个测试函数独立的数据库会话"""
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_user(db):
    """创建测试用户"""
    from app.models.user import User
    from app.utils.security import hash_password

    user = User(
        phone="13800138000",
        nickname="测试用户",
        password_hash=hash_password("test123"),
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def sample_merchant(db):
    """创建测试商家"""
    from app.models.merchant import Merchant
    from app.utils.security import hash_password

    merchant = Merchant(
        phone="13900139000",
        store_name="测试商家",
        password_hash=hash_password("test123"),
        status=1,  # 已审核
        latitude=22.5431,
        longitude=113.9614,
        city="深圳",
        district="南山区",
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@pytest.fixture
def sample_box(db, sample_merchant):
    """创建测试盲盒"""
    from app.models.mystery_box import MysteryBox, BoxTag

    box = MysteryBox(
        merchant_id=sample_merchant.id,
        title="测试盲盒-中式快餐",
        description="今日中式快餐剩余，原价35元",
        box_type="surplus",
        original_price=35.00,
        sale_price=19.90,
        stock=5,
        total_stock=10,
        status=1,
    )
    db.add(box)
    db.commit()
    db.refresh(box)

    # 添加标签
    tag = BoxTag(box_id=box.id, tag_name="中式快餐")
    db.add(tag)
    db.commit()

    return box


# ========== Auth Service Tests ==========
class TestAuthService:
    def test_send_sms_code(self, db):
        from app.services.auth_service import send_sms_code, verify_sms_code

        phone = "13800138000"
        code = send_sms_code(phone)  # send_sms_code 返回生成的验证码
        assert verify_sms_code(phone, code) is True
        assert verify_sms_code(phone, "000000") is False

    def test_login_by_password_success(self, db, sample_user):
        from app.services.auth_service import login_by_password

        result = login_by_password("13800138000", "test123", db)
        # TokenResponse 是 Pydantic 模型
        assert result.access_token is not None
        assert result.refresh_token is not None

    def test_login_by_password_wrong(self, db, sample_user):
        from app.services.auth_service import login_by_password

        with pytest.raises(ValueError):
            login_by_password("13800138000", "wrong_password", db)

    def test_login_nonexistent_user(self, db):
        from app.services.auth_service import login_by_password

        with pytest.raises(ValueError):
            login_by_password("99999999999", "test123", db)


# ========== Box Service Tests ==========
class TestBoxService:
    def test_create_box(self, db, sample_merchant):
        from app.services.box_service import create_box
        from app.schemas.mystery_box import BoxCreate

        data = BoxCreate(
            title="测试盲盒",
            description="测试描述",
            box_type="surplus",
            original_price=30.00,
            sale_price=15.00,
            stock=10,
            total_stock=20,
            tags=["中式快餐", "麻辣"],
            pick_up_start="09:00",
            pick_up_end="21:00",
        )
        box = create_box(sample_merchant.id, data, db)
        assert box.title == "测试盲盒"
        assert box.sale_price == 15.00
        assert box.status == 1

    def test_get_box_list(self, db, sample_box):
        from app.services.box_service import get_box_list
        from app.schemas.mystery_box import BoxListQuery

        query = BoxListQuery(page=1, size=10)
        items, total = get_box_list(query, db)
        assert total >= 1
        assert len(items) >= 1

    def test_get_box_detail(self, db, sample_box):
        from app.services.box_service import get_box_detail

        detail = get_box_detail(sample_box.id, db)
        assert detail["title"] == "测试盲盒-中式快餐"
        assert detail["box_type"] == "surplus"

    def test_update_box(self, db, sample_box, sample_merchant):
        from app.services.box_service import update_box
        from app.schemas.mystery_box import BoxUpdate

        data = BoxUpdate(title="已更新盲盒")
        box = update_box(sample_box.id, sample_merchant.id, data, db)
        assert box.title == "已更新盲盒"

    def test_get_nearby_boxes(self, db, sample_box):
        from app.services.box_service import get_nearby_boxes

        boxes = get_nearby_boxes(22.5431, 113.9614, 5000, db)
        assert len(boxes) >= 1

    def test_recommend_boxes(self, db, sample_user, sample_box):
        from app.services.matching_service import recommend_boxes

        results = recommend_boxes(sample_user.id, 22.5431, 113.9614, 5000, 10, db)
        assert isinstance(results, list)


# ========== Order Service Tests ==========
class TestOrderService:
    @pytest.fixture
    def sample_address(self, db, sample_user):
        from app.models.user import UserAddress

        addr = UserAddress(
            user_id=sample_user.id,
            contact_name="测试联系人",
            contact_phone="13800138000",
            province="广东",
            city="深圳",
            district="南山区",
            detail="科技园路1号",
            latitude=22.5431,
            longitude=113.9614,
        )
        db.add(addr)
        db.commit()
        db.refresh(addr)
        return addr

    def test_create_order(self, db, sample_user, sample_box, sample_address):
        from app.services.order_service import create_order
        from app.schemas.order import OrderCreate

        data = OrderCreate(box_id=sample_box.id, address_id=sample_address.id, quantity=1)
        order = create_order(sample_user.id, data, db)

        assert order.order_no.startswith("ord")
        assert order.order_status == "pending_pay"
        assert order.paid_amount > 0

    def test_order_status_transition_valid(self, db, sample_user, sample_box, sample_address):
        from app.services.order_service import create_order, update_order_status
        from app.schemas.order import OrderCreate

        data = OrderCreate(box_id=sample_box.id, address_id=sample_address.id, quantity=1)
        order = create_order(sample_user.id, data, db)

        # pending_pay -> paid
        updated = update_order_status(order.id, "paid", db)
        assert updated.order_status == "paid"

    def test_order_status_transition_invalid(self, db, sample_user, sample_box, sample_address):
        from app.services.order_service import create_order, update_order_status
        from app.schemas.order import OrderCreate

        data = OrderCreate(box_id=sample_box.id, address_id=sample_address.id, quantity=1)
        order = create_order(sample_user.id, data, db)

        # pending_pay -> delivering is invalid
        with pytest.raises(ValueError):
            update_order_status(order.id, "delivering", db)


# ========== Model Tests ==========
class TestModels:
    def test_user_creation(self, db):
        from app.models.user import User
        from app.utils.security import hash_password

        user = User(phone="13600136000", password_hash=hash_password("test"), nickname="测试")
        db.add(user)
        db.commit()

        saved = db.query(User).filter_by(phone="13600136000").first()
        assert saved is not None
        assert saved.nickname == "测试"

    def test_merchant_creation(self, db):
        from app.models.merchant import Merchant
        from app.utils.security import hash_password

        merchant = Merchant(
            phone="13500135000",
            store_name="测试店铺",
            password_hash=hash_password("test"),
        )
        db.add(merchant)
        db.commit()

        saved = db.query(Merchant).filter_by(phone="13500135000").first()
        assert saved is not None
        assert saved.status == 0  # 默认待审核
