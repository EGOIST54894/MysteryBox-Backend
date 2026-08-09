"""
API v1 路由聚合模块
将所有子路由注册到同一个 APIRouter 上，方便在 main.py 中挂载。
"""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.boxes import router as boxes_router
from app.api.v1.community import router as community_router
from app.api.v1.delivery import router as delivery_router
from app.api.v1.draw import router as draw_router
from app.api.v1.merchant import router as merchant_router
from app.api.v1.messages import router as messages_router
from app.api.v1.mock_pay import router as mock_pay_router
from app.api.v1.orders import router as orders_router
from app.api.v1.payments import router as payments_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.users import router as users_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["认证"])
router.include_router(admin_router, prefix="", tags=["管理后台"])
router.include_router(boxes_router, prefix="", tags=["盲盒"])
router.include_router(community_router, prefix="", tags=["社区"])
router.include_router(draw_router, prefix="", tags=["抽卡"])
router.include_router(merchant_router, prefix="", tags=["商家"])
router.include_router(orders_router, prefix="/orders", tags=["订单"])
router.include_router(payments_router, prefix="/payments", tags=["支付"])
router.include_router(reviews_router, prefix="/reviews", tags=["评价"])
router.include_router(users_router, prefix="/users", tags=["用户"])
router.include_router(delivery_router, prefix="", tags=["配送"])
router.include_router(messages_router, prefix="/messages", tags=["消息"])

# 模拟支付页面直接挂载到根路径（/mock-pay?order_id=...）
router.include_router(mock_pay_router, tags=["模拟支付"])
