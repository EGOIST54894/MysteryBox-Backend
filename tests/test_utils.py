"""单元测试：工具函数"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_sms_code,
)
from app.utils.response import success_response, error_response, paginated_response
from app.utils.geo import haversine_distance, is_within_radius, format_distance


# ========== 安全工具测试 ==========
class TestSecurityUtils:
    """密码和JWT工具测试"""

    def test_hash_and_verify_password(self):
        """密码哈希和验证"""
        password = "test123456"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False

    def test_hash_password_deterministic(self):
        """bcrypt每次生成不同的哈希"""
        h1 = hash_password("test")
        h2 = hash_password("test")
        assert h1 != h2  # bcrypt salt makes each hash unique
        assert verify_password("test", h1) is True
        assert verify_password("test", h2) is True

    def test_create_and_decode_access_token(self):
        """创建和解码Access Token"""
        token = create_access_token({"user_id": 1, "role": "user"})
        assert isinstance(token, str)
        assert len(token) > 20

        payload = decode_token(token)
        assert payload["user_id"] == 1
        assert payload["role"] == "user"

    def test_create_and_decode_refresh_token(self):
        """创建和解码Refresh Token"""
        token = create_refresh_token({"user_id": 1, "role": "user"})
        payload = decode_token(token)
        assert payload["user_id"] == 1

    def test_token_type_claim(self):
        """Access和Refresh Token有不同type声明"""
        access = create_access_token({"user_id": 1, "role": "user"})
        refresh = create_refresh_token({"user_id": 1, "role": "user"})

        a = decode_token(access)
        r = decode_token(refresh)

        assert a.get("type") == "access"
        assert r.get("type") == "refresh"

    def test_generate_sms_code(self):
        """生成6位数字验证码"""
        code = generate_sms_code()
        assert len(code) == 6
        assert code.isdigit()
        assert 0 <= int(code) <= 999999

        # 多次生成确保随机性
        codes = {generate_sms_code() for _ in range(20)}
        assert len(codes) > 1  # 不太可能20次都相同


# ========== 响应格式测试 ==========
class TestResponseUtils:
    """统一响应格式测试"""

    def test_success_response(self):
        resp = success_response({"name": "测试"})
        assert resp["code"] == 0
        assert resp["message"] == "success"
        assert resp["data"]["name"] == "测试"

    def test_success_response_custom_message(self):
        resp = success_response(None, "操作成功")
        assert resp["code"] == 0
        assert resp["message"] == "操作成功"
        assert resp["data"] is None

    def test_error_response(self):
        resp = error_response(1001, "手机号已注册")
        assert resp["code"] == 1001
        assert resp["message"] == "手机号已注册"
        assert resp["data"] is None

    def test_error_response_with_data(self):
        resp = error_response(500, "服务器内部错误")
        assert resp["code"] == 500
        assert resp["message"] == "服务器内部错误"
        assert resp["data"] is None

    def test_paginated_response(self):
        resp = paginated_response([{"id": 1}, {"id": 2}], 100, 1, 10)
        assert resp["code"] == 0
        assert len(resp["data"]["items"]) == 2
        assert resp["data"]["pagination"]["total"] == 100
        assert resp["data"]["pagination"]["page"] == 1
        assert resp["data"]["pagination"]["size"] == 10
        assert resp["data"]["pagination"]["total_pages"] == 10


# ========== 地理计算测试 ==========
class TestGeoUtils:
    """地理计算工具测试"""

    def test_haversine_same_point(self):
        """相同坐标距离为0"""
        d = haversine_distance(22.5431, 113.9614, 22.5431, 113.9614)
        assert d == 0.0

    def test_haversine_shenzhen(self):
        """深圳两个已知点距离"""
        # 深圳湾公园 → 世界之窗（约5km）
        d = haversine_distance(22.515, 113.944, 22.536, 113.973)
        # 实际约3.5km
        assert 2000 < d < 5000

    def test_haversine_beijing(self):
        """北京天安门 → 故宫（约1km）"""
        d = haversine_distance(39.9042, 116.3974, 39.9137, 116.3974)
        assert 800 < d < 1200

    def test_is_within_radius(self):
        """半径范围检查"""
        lat, lng = 22.5431, 113.9614
        assert is_within_radius(lat, lng, lat + 0.001, lng + 0.001, 500) is True
        assert is_within_radius(lat, lng, lat + 1, lng + 1, 100) is False

    def test_format_distance_meters(self):
        """距离格式化 - 米"""
        assert format_distance(500) == "500m"
        assert format_distance(999) == "999m"

    def test_format_distance_kilometers(self):
        """距离格式化 - 千米"""
        assert format_distance(1000) == "1.0km"
        assert format_distance(1500) == "1.5km"
        assert format_distance(2345) == "2.3km"

    def test_format_distance_zero(self):
        """距离格式化 - 零"""
        assert format_distance(0) == "0m"


# ========== 配置测试 ==========
class TestConfig:
    """应用配置测试"""

    def test_settings_load(self):
        from app.config import settings

        assert settings.APP_NAME == "外卖盲盒"
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert settings.SMS_CODE_LENGTH == 6

    def test_secret_key_exists(self):
        from app.config import settings

        assert len(settings.SECRET_KEY) > 0
