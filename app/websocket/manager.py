"""
WebSocket 连接管理器

管理所有 WebSocket 连接，按订单ID分组，支持：
- 订单状态变更推送（order 分组）
- 配送员位置追踪推送（tracking 分组）
- 心跳保活机制（30秒超时自动断开）
- 客户端断开时自动清理连接
"""

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 心跳超时时间（秒）
HEARTBEAT_TIMEOUT = 30
# 位置推送间隔（秒）
LOCATION_PUSH_INTERVAL = 15


class ConnectionManager:
    """
    WebSocket 连接管理器（单例模式）。

    按功能分为两组连接：
    - order_connections: 订单状态变更推送（配送员端和用户端都监听）
      结构: {order_id: {websocket: last_heartbeat_timestamp}}
    - tracking_connections: 配送员位置追踪（用户端监听）
      结构: {order_id: {websocket: last_heartbeat_timestamp}}
    """

    def __init__(self):
        # 订单状态监听连接组: order_id -> {WebSocket -> last_heartbeat}
        self.order_connections: dict[str, dict[WebSocket, float]] = {}
        # 配送追踪监听连接组: order_id -> {WebSocket -> last_heartbeat}
        self.tracking_connections: dict[str, dict[WebSocket, float]] = {}
        # 锁，保证并发安全
        self._lock = asyncio.Lock()

    async def connect_order(self, order_id: str, websocket: WebSocket) -> None:
        """
        建立订单状态监听连接。

        客户端（配送员或用户）连接到此通道后，将实时收到订单状态变更推送。

        Args:
            order_id: 订单ID（字符串形式）
            websocket: WebSocket 连接实例
        """
        await websocket.accept()
        async with self._lock:
            if order_id not in self.order_connections:
                self.order_connections[order_id] = {}
            self.order_connections[order_id][websocket] = time.time()
        logger.info(f"[订单WebSocket] 新连接建立: order_id={order_id}, "
                     f"当前该订单连接数={len(self.order_connections[order_id])}")

    async def connect_tracking(self, order_id: str, websocket: WebSocket) -> None:
        """
        建立配送追踪连接。

        用户端连接到此通道后，将定期接收配送员实时位置推送。

        Args:
            order_id: 订单ID（字符串形式）
            websocket: WebSocket 连接实例
        """
        await websocket.accept()
        async with self._lock:
            if order_id not in self.tracking_connections:
                self.tracking_connections[order_id] = {}
            self.tracking_connections[order_id][websocket] = time.time()
        logger.info(f"[追踪WebSocket] 新连接建立: order_id={order_id}, "
                     f"当前该订单追踪连接数={len(self.tracking_connections[order_id])}")

    async def disconnect(self, order_id: str, websocket: WebSocket) -> None:
        """
        断开指定连接的 WebSocket 并清理。

        同时从 order_connections 和 tracking_connections 中移除。

        Args:
            order_id: 订单ID（字符串形式）
            websocket: 要移除的 WebSocket 连接
        """
        async with self._lock:
            # 从订单状态监听组中移除
            if order_id in self.order_connections:
                self.order_connections[order_id].pop(websocket, None)
                if not self.order_connections[order_id]:
                    del self.order_connections[order_id]
                    logger.info(f"[订单WebSocket] order_id={order_id} 的所有连接已清理")
                else:
                    logger.info(f"[订单WebSocket] 连接断开: order_id={order_id}, "
                                 f"剩余连接数={len(self.order_connections.get(order_id, {}))}")

            # 从配送追踪组中移除
            if order_id in self.tracking_connections:
                self.tracking_connections[order_id].pop(websocket, None)
                if not self.tracking_connections[order_id]:
                    del self.tracking_connections[order_id]
                    logger.info(f"[追踪WebSocket] order_id={order_id} 的所有追踪连接已清理")
                else:
                    logger.info(f"[追踪WebSocket] 连接断开: order_id={order_id}, "
                                 f"剩余追踪连接数={len(self.tracking_connections.get(order_id, {}))}")

        # 尝试关闭 WebSocket（可能已经断开，忽略异常）
        try:
            await websocket.close()
        except Exception:
            pass

    async def send_order_update(self, order_id: str, message: dict) -> None:
        """
        向指定订单的所有监听连接推送订单状态变更消息。

        消息格式:
            {"type": "order_update", "data": {...}, "timestamp": ...}

        Args:
            order_id: 订单ID（字符串形式）
            message: 要推送的消息数据（data 部分）
        """
        payload = {
            "type": "order_update",
            "data": message,
            "timestamp": int(time.time()),
        }

        async with self._lock:
            connections = self.order_connections.get(order_id, {})

        # 在锁外发送消息，避免阻塞
        disconnected = []
        for ws in list(connections.keys()):
            try:
                await ws.send_json(payload)
                # 更新心跳时间
                connections[ws] = time.time()
            except Exception:
                disconnected.append(ws)

        # 清理已断开的连接
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self.order_connections.get(order_id, {}).pop(ws, None)
                if order_id in self.order_connections and not self.order_connections[order_id]:
                    del self.order_connections[order_id]

    async def send_location_update(self, order_id: str, message: dict) -> None:
        """
        向指定订单的所有追踪连接推送配送员位置更新。

        消息格式:
            {"type": "location_update", "data": {...}, "timestamp": ...}

        Args:
            order_id: 订单ID（字符串形式）
            message: 要推送的位置数据（包含 lat, lng 等）
        """
        payload = {
            "type": "location_update",
            "data": message,
            "timestamp": int(time.time()),
        }

        async with self._lock:
            connections = self.tracking_connections.get(order_id, {})

        disconnected = []
        for ws in list(connections.keys()):
            try:
                await ws.send_json(payload)
                connections[ws] = time.time()
            except Exception:
                disconnected.append(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self.tracking_connections.get(order_id, {}).pop(ws, None)
                if order_id in self.tracking_connections and not self.tracking_connections[order_id]:
                    del self.tracking_connections[order_id]

    async def broadcast_to_all(self, message: dict) -> None:
        """
        向所有已连接的 WebSocket 客户端广播通知消息。

        消息格式:
            {"type": "notification", "data": {...}, "timestamp": ...}

        用于系统级通知（如：系统维护公告、活动推送等）。

        Args:
            message: 要广播的消息数据
        """
        payload = {
            "type": "notification",
            "data": message,
            "timestamp": int(time.time()),
        }

        async with self._lock:
            all_order_conns = dict(self.order_connections)
            all_tracking_conns = dict(self.tracking_connections)

        # 收集所有唯一的 WebSocket 连接
        all_ws: set[WebSocket] = set()
        for conns in all_order_conns.values():
            all_ws.update(conns.keys())
        for conns in all_tracking_conns.values():
            all_ws.update(conns.keys())

        disconnected = set()
        for ws in all_ws:
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.add(ws)

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                for order_id in list(self.order_connections.keys()):
                    for ws in list(self.order_connections[order_id].keys()):
                        if ws in disconnected:
                            self.order_connections[order_id].pop(ws, None)
                    if order_id in self.order_connections and not self.order_connections[order_id]:
                        del self.order_connections[order_id]

                for order_id in list(self.tracking_connections.keys()):
                    for ws in list(self.tracking_connections[order_id].keys()):
                        if ws in disconnected:
                            self.tracking_connections[order_id].pop(ws, None)
                    if order_id in self.tracking_connections and not self.tracking_connections[order_id]:
                        del self.tracking_connections[order_id]

    async def cleanup_stale_connections(self) -> int:
        """
        清理超时的僵死连接（心跳超过 HEARTBEAT_TIMEOUT 秒未更新的连接）。

        该方法应由后台定时任务周期性调用（如每10秒一次）。

        Returns:
            清理的连接总数
        """
        now = time.time()
        stale_ws: list[tuple[str, WebSocket, str]] = []  # (order_id, ws, group_type)

        async with self._lock:
            # 检查订单状态监听组
            for order_id, conns in self.order_connections.items():
                for ws, last_hb in list(conns.items()):
                    if now - last_hb > HEARTBEAT_TIMEOUT:
                        stale_ws.append((order_id, ws, "order"))

            # 检查配送追踪组
            for order_id, conns in self.tracking_connections.items():
                for ws, last_hb in list(conns.items()):
                    if now - last_hb > HEARTBEAT_TIMEOUT:
                        stale_ws.append((order_id, ws, "tracking"))

            # 执行清理
            for order_id, ws, group_type in stale_ws:
                if group_type == "order":
                    self.order_connections[order_id].pop(ws, None)
                    if not self.order_connections[order_id]:
                        del self.order_connections[order_id]
                else:
                    self.tracking_connections[order_id].pop(ws, None)
                    if not self.tracking_connections[order_id]:
                        del self.tracking_connections[order_id]

        # 关闭清理掉的连接
        for _, ws, _ in stale_ws:
            try:
                await ws.close()
            except Exception:
                pass

        if stale_ws:
            logger.info(f"[WebSocket清理] 清理了 {len(stale_ws)} 个超时连接")
        return len(stale_ws)

    def get_connection_stats(self) -> dict[str, Any]:
        """
        获取当前连接统计信息，用于监控和调试。

        Returns:
            包含各分组连接数的字典
        """
        total_order_conns = sum(len(conns) for conns in self.order_connections.values())
        total_tracking_conns = sum(len(conns) for conns in self.tracking_connections.values())
        return {
            "order_group_count": len(self.order_connections),
            "total_order_connections": total_order_conns,
            "tracking_group_count": len(self.tracking_connections),
            "total_tracking_connections": total_tracking_conns,
            "total_connections": total_order_conns + total_tracking_conns,
        }
