"""pytest 配置和共享 fixtures"""
import sys
import os

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.dependencies import get_db

# ========== 测试数据库 ==========
# 使用 SQLite 内存数据库进行测试
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库会话，每次测试后回滚"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client():
    """创建 FastAPI TestClient"""
    from app.main import app

    # 覆盖依赖：使用测试数据库
    def override_get_db():
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.rollback()
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {"phone": "13800138000", "nickname": "测试用户", "password": "test123456"}


@pytest.fixture
def sample_merchant_data():
    """示例商家数据"""
    return {
        "phone": "13900139000",
        "store_name": "测试商家",
        "password": "test123456",
        "category": "中式快餐",
        "latitude": 22.5431,
        "longitude": 113.9614,
        "address_detail": "深圳市南山区科技园",
    }


@pytest.fixture
def auth_headers(client, sample_user_data):
    """获取已登录用户的认证头"""
    # 先注册
    client.post("/api/v1/auth/send-sms", json={"phone": sample_user_data["phone"]})
    client.post(
        "/api/v1/auth/register",
        json={
            "phone": sample_user_data["phone"],
            "sms_code": "888888",
            "nickname": sample_user_data["nickname"],
            "password": sample_user_data["password"],
        },
    )
    # 登录
    resp = client.post(
        "/api/v1/auth/login/password",
        json={
            "phone": sample_user_data["phone"],
            "password": sample_user_data["password"],
        },
    )
    data = resp.json()
    token = data.get("data", {}).get("access_token", "")
    return {"Authorization": f"Bearer {token}"}
