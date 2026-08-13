"""
FastAPI 应用入口
创建应用实例，注册中间件、路由，配置全局异常处理与生命周期事件。
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.websocket.manager import ConnectionManager

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时创建必要目录和 WebSocket 管理器，关闭时清理资源"""
    # ---- 启动阶段 ----
    logger.info(f"🚀 {settings.APP_NAME} v{settings.VERSION} 正在启动...")
    logger.info(f"   数据库: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    logger.info(f"   上传目录: {settings.upload_dir_path}")
    logger.info(f"   支付模式: {settings.PAYMENT_MODE}")
    logger.info(f"   调试模式: {settings.DEBUG}")

    # 确保数据库表已创建（新增的表会自动创建，已有的表不会重复创建）
    # 注意：必须先导入所有模型再 create_all，确保新表（如 message）被创建
    from app.models.base import Base, engine
    from app import models as _models  # noqa: F401 — 触发所有模型注册
    Base.metadata.create_all(bind=engine)
    logger.info("   数据库表已就绪")

    # 确保上传目录存在
    settings.upload_dir_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"   上传目录已就绪: {settings.upload_dir_path}")

    # 创建 WebSocket ConnectionManager 单例并挂载到 app.state
    websocket_manager = ConnectionManager()
    app.state.websocket_manager = websocket_manager
    logger.info("   WebSocket ConnectionManager 已初始化")

    # 启动后台任务：定期清理僵死 WebSocket 连接（每 30 秒执行一次）
    cleanup_task = asyncio.create_task(_cleanup_stale_ws_connections(websocket_manager))

    yield  # 应用运行中

    # ---- 关闭阶段 ----
    logger.info(f"👋 {settings.APP_NAME} 正在关闭...")

    # 取消后台清理任务
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("   WebSocket 后台清理任务已停止")


# ==================== WebSocket 后台清理任务 ====================

async def _cleanup_stale_ws_connections(manager: ConnectionManager):
    """
    后台定时清理 WebSocket 僵死连接。

    每 30 秒执行一次，清理心跳超时的连接，
    防止内存泄漏和无效连接堆积。
    """
    while True:
        try:
            await asyncio.sleep(30)
            cleaned = await manager.cleanup_stale_connections()
            if cleaned > 0:
                logger.debug(f"WebSocket 清理完成，移除 {cleaned} 个僵死连接")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"WebSocket 清理任务异常: {e}")


# ==================== 创建 FastAPI 应用实例 ====================
app = FastAPI(
    title=settings.APP_NAME,
    description="外卖盲盒 - 让每一餐都充满惊喜！在线点餐与配送服务平台",
    version=settings.VERSION,
    lifespan=lifespan,
)

# ==================== CORS 跨域中间件 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 静态文件挂载（上传文件访问） ====================
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir_path)), name="uploads")


# ==================== 全局异常处理 ====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常捕获，统一返回 JSON 格式错误"""
    logger.exception(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None,
        },
    )


# ==================== 健康检查接口 ====================
@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查端点，用于服务探活"""
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "app_name": settings.APP_NAME,
            "version": settings.VERSION,
            "status": "healthy",
        },
    }


@app.get("/", tags=["系统"])
async def root():
    """根路径，返回欢迎信息"""
    return {
        "code": 200,
        "message": "欢迎使用外卖盲盒API",
        "data": {
            "app_name": settings.APP_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
        },
    }


# ==================== 注册 API 路由 ====================
from app.api.v1 import router as v1_router
from app.websocket.handlers import router as ws_router

app.include_router(v1_router, prefix="/api/v1")
app.include_router(ws_router)  # WebSocket 路由（无 prefix）


# ==================== 程序入口 ====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
