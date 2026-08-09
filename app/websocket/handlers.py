"""
WebSocket 路由处理器

定义 WebSocket 端点，处理连接建立、心跳保活、消息收发和断开清理。

端点：
- /ws/orders/{order_id}      — 订单状态变更监听（配送员端 + 用户端）
- /ws/delivery/track/{order_id} — 配送员位置追踪（用户端）
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import jwt
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.delivery import DeliveryPersonnel
from app.models.order import DeliveryOrder

logger = logging.getLogger(__name__)

router = APIRouter()

# 心跳超时（秒）
HEARTBEAT_TIMEOUT = 30
# 位置推送间隔（秒）
LOCATION_PUSH_INTERVAL = 15


def _verify_token(token: str) -> dict:
    """
    验证 JWT Token 并返回 payload。

    Args:
        token: JWT token 字符串

    Returns:
        payload 字典

    Raises:
        RuntimeError: token 无效
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except PyJWTError:
        raise RuntimeError("无效的认证凭证")


@router.websocket("/ws/orders/{order_id}")
async def websocket_order(
    websocket: WebSocket,
    order_id: str,
    token: str = Query(..., description="JWT认证Token"),
):
    """
    订单状态变更 WebSocket 通道。

    配送员端和用户端均可连接此通道，实时接收订单状态变更推送。
    收到消息类型：
        - "order_update": 订单状态变更通知

    客户端需定时发送 ping 消息以保持连接，超时 30 秒自动断开。

    连接流程：
        1. 验证 token
        2. 注册到 ConnectionManager 的 order_connections
        3. 发送欢迎消息
        4. 循环等待客户端消息（处理 pong/heartbeat）
        5. 断开时自动清理
    """
    # 获取 ConnectionManager 单例（从 app.state 中获取）
    from app.main import app
    manager = app.state.websocket_manager

    # 验证 token
    try:
        payload = _verify_token(token)
    except RuntimeError:
        await websocket.close(code=4001, reason="无效的认证凭证")
        return

    user_id = payload.get("sub")
    role = payload.get("role")
    logger.info(f"[订单WebSocket] 用户 {user_id}({role}) 连接订单 {order_id}")

    # 建立连接
    await manager.connect_order(order_id, websocket)

    try:
        # 发送欢迎消息，确认连接成功
        await websocket.send_json({
            "type": "connected",
            "data": {
                "order_id": order_id,
                "message": "已连接到订单状态推送通道",
                "server_time": datetime.now(timezone.utc).isoformat(),
            },
            "timestamp": int(time.time()),
        })

        # 消息循环：处理客户端心跳和消息
        while True:
            try:
                # 等待客户端消息，超时时间为心跳间隔的一半
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=HEARTBEAT_TIMEOUT / 2,
                )

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    # 客户端心跳，回复 pong
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": int(time.time()),
                    })
                    # 更新心跳时间（在 manager 的连接字典中）
                    async with manager._lock:
                        if order_id in manager.order_connections:
                            manager.order_connections[order_id][websocket] = time.time()

                elif msg_type == "pong":
                    # 客户端响应 pong，更新心跳时间
                    async with manager._lock:
                        if order_id in manager.order_connections:
                            manager.order_connections[order_id][websocket] = time.time()

                else:
                    # 未知消息类型，忽略
                    logger.debug(f"[订单WebSocket] 收到未知消息类型: {msg_type}")

            except asyncio.TimeoutError:
                # 超时未收到消息，发送 ping 检测客户端是否存活
                try:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": int(time.time()),
                    })
                except Exception:
                    # 发送失败，客户端可能已断开
                    logger.info(f"[订单WebSocket] ping 发送失败，order_id={order_id}，客户端可能已断开")
                    break

    except WebSocketDisconnect:
        logger.info(f"[订单WebSocket] 客户端主动断开: order_id={order_id}")
    except Exception as e:
        logger.error(f"[订单WebSocket] 异常: order_id={order_id}, error={e}")
    finally:
        # 清理连接
        await manager.disconnect(order_id, websocket)


@router.websocket("/ws/delivery/track/{order_id}")
async def websocket_delivery_track(
    websocket: WebSocket,
    order_id: str,
    token: str = Query(..., description="JWT认证Token"),
):
    """
    配送追踪 WebSocket 通道。

    用户端连接此通道，每 15 秒自动接收配送员的实时位置更新。
    收到消息类型：
        - "location_update": 配送员位置更新

    推送逻辑：
        1. 服务端周期性查询配送员当前位置（从数据库 delivery_personnel 表）
        2. 如果位置有变化，推送给所有监听该订单的追踪连接
        3. 如果没有配送员信息或配送已完成，推送相应状态消息

    连接流程：
        1. 验证 token
        2. 注册到 ConnectionManager 的 tracking_connections
        3. 发送欢迎消息
        4. 每 15 秒推送一次配送员位置
        5. 断开时自动清理
    """
    from app.main import app
    manager = app.state.websocket_manager

    # 验证 token
    try:
        payload = _verify_token(token)
    except RuntimeError:
        await websocket.close(code=4001, reason="无效的认证凭证")
        return

    user_id = payload.get("sub")
    role = payload.get("role")
    logger.info(f"[追踪WebSocket] 用户 {user_id}({role}) 追踪订单 {order_id}")

    # 建立连接
    await manager.connect_tracking(order_id, websocket)

    # 上次推送的位置（用于判断位置是否变化）
    last_lat = None
    last_lng = None

    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "connected",
            "data": {
                "order_id": order_id,
                "message": "已连接到配送追踪通道",
                "server_time": datetime.now(timezone.utc).isoformat(),
            },
            "timestamp": int(time.time()),
        })

        # 主循环：周期推送位置 + 处理心跳
        async def handle_client_messages():
            """处理客户端消息（心跳）的协程"""
            nonlocal last_lat, last_lng
            while True:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=5,  # 短超时，方便定期检查
                    )
                    msg_type = data.get("type", "")
                    if msg_type == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": int(time.time()),
                        })
                        # 更新心跳
                        async with manager._lock:
                            if order_id in manager.tracking_connections:
                                manager.tracking_connections[order_id][websocket] = time.time()
                except asyncio.TimeoutError:
                    # 短超时是正常的，继续循环
                    continue
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        async def push_location_updates():
            """周期推送配送员位置的协程"""
            nonlocal last_lat, last_lng

            # 等待一小段时间再开始推送
            await asyncio.sleep(2)

            while True:
                try:
                    # 检查当前连接是否还存活
                    async with manager._lock:
                        if order_id not in manager.tracking_connections:
                            break
                        if websocket not in manager.tracking_connections.get(order_id, {}):
                            break

                    # 查询配送员当前位置（需要数据库会话）
                    from app.dependencies import get_db
                    db: Session = next(get_db())
                    try:
                        # 查找该订单的配送信息
                        delivery_order = (
                            db.query(DeliveryOrder)
                            .filter(DeliveryOrder.order_id == int(order_id))
                            .first()
                        )

                        if not delivery_order:
                            await websocket.send_json({
                                "type": "location_update",
                                "data": {
                                    "order_id": order_id,
                                    "status": "no_delivery",
                                    "message": "该订单暂无配送信息",
                                },
                                "timestamp": int(time.time()),
                            })
                        elif delivery_order.status == "delivered":
                            # 已送达，通知用户并停止推送
                            await websocket.send_json({
                                "type": "location_update",
                                "data": {
                                    "order_id": order_id,
                                    "status": "delivered",
                                    "message": "订单已送达",
                                    "delivered_at": delivery_order.delivered_at.isoformat() if delivery_order.delivered_at else None,
                                },
                                "timestamp": int(time.time()),
                            })
                            break  # 已送达，停止推送
                        else:
                            # 获取配送员实时位置
                            dp = delivery_order.delivery_person
                            if dp and dp.current_lat is not None and dp.current_lng is not None:
                                new_lat = float(dp.current_lat)
                                new_lng = float(dp.current_lng)

                                # 仅位置有变化时才推送
                                if new_lat != last_lat or new_lng != last_lng:
                                    last_lat, last_lng = new_lat, new_lng
                                    await websocket.send_json({
                                        "type": "location_update",
                                        "data": {
                                            "order_id": order_id,
                                            "delivery_person_id": dp.id,
                                            "name": dp.real_name,
                                            "latitude": new_lat,
                                            "longitude": new_lng,
                                            "delivery_status": delivery_order.status,
                                        },
                                        "timestamp": int(time.time()),
                                    })
                            else:
                                # 配送员尚未上传位置
                                await websocket.send_json({
                                    "type": "location_update",
                                    "data": {
                                        "order_id": order_id,
                                        "status": "no_location",
                                        "message": "配送员位置信息暂未更新",
                                        "delivery_status": delivery_order.status,
                                    },
                                    "timestamp": int(time.time()),
                                })
                    finally:
                        db.close()

                    # 等待下一次推送
                    await asyncio.sleep(LOCATION_PUSH_INTERVAL)

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"[追踪WebSocket位置推送] 异常: order_id={order_id}, error={e}")
                    await asyncio.sleep(LOCATION_PUSH_INTERVAL)

        # 并发运行两个协程：处理客户端消息 + 推送位置
        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_location_updates())

        # 等待任一任务完成（如果客户端断开，client_task 会先结束）
        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 取消未完成的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info(f"[追踪WebSocket] 客户端主动断开: order_id={order_id}")
    except Exception as e:
        logger.error(f"[追踪WebSocket] 异常: order_id={order_id}, error={e}")
    finally:
        await manager.disconnect(order_id, websocket)
