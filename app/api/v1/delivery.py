"""
配送员端 API 路由

提供配送员接单、取餐、送达、位置上报、订单查询、统计等接口。
所有端点均需配送员认证（依赖 get_current_delivery）。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_delivery, get_db
from app.models.delivery import DeliveryPersonnel
from app.models.order import DeliveryOrder
from app.services import delivery_service
from app.utils.response import error_response, paginated_response, success_response

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────── Pydantic 请求模型 ────────────────────────────

class LocationUpdate(BaseModel):
    """配送员位置更新请求体"""
    lat: float = Field(..., ge=-90, le=90, description="当前纬度")
    lng: float = Field(..., ge=-180, le=180, description="当前经度")


# ──────────────────────────── 辅助函数 ────────────────────────────

async def _get_websocket_manager(request: Request):
    """从 app.state 获取 WebSocket ConnectionManager 单例"""
    return request.app.state.websocket_manager


async def _notify_order_update(request: Request, order_id: int, data: dict):
    """通过 WebSocket 推送订单状态变更通知"""
    try:
        manager = request.app.state.websocket_manager
        await manager.send_order_update(str(order_id), data)
    except Exception as e:
        logger.error(f"WebSocket 订单推送失败 order_id={order_id}: {e}")


async def _notify_location_update(request: Request, order_id: int, data: dict):
    """通过 WebSocket 推送配送员位置更新"""
    try:
        manager = request.app.state.websocket_manager
        await manager.send_location_update(str(order_id), data)
    except Exception as e:
        logger.error(f"WebSocket 位置推送失败 order_id={order_id}: {e}")


async def _notify_new_message(request: Request, order_id: int, content: str,
                              sender_name: str = "", sender_role: str = "delivery"):
    """通过 WebSocket 推送新消息通知（群聊）"""
    try:
        manager = request.app.state.websocket_manager
        await manager.send_message(str(order_id), {
            "order_id": order_id,
            "content": content,
            "sender_name": sender_name,
            "sender_role": sender_role,
            "message_type": "system",
        })
    except Exception as e:
        logger.error(f"WebSocket 消息推送失败 order_id={order_id}: {e}")


# ──────────────────────────── API 端点 ────────────────────────────

@router.get("/delivery/orders/available", summary="获取可接订单列表")
async def get_available_orders(
    lat: float = Query(..., ge=-90, le=90, description="配送员当前纬度"),
    lng: float = Query(..., ge=-180, le=180, description="配送员当前经度"),
    radius: float = Query(5000, ge=100, le=50000, description="搜索半径（米），默认5000m"),
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    获取配送员附近可接的订单列表。

    返回状态为 ready_pickup 且未被接单的订单，
    按配送员到商家（取餐点）的距离升序排列。
    需要传入配送员当前经纬度坐标。
    """
    try:
        orders = delivery_service.get_available_orders(
            lat=lat,
            lng=lng,
            radius=radius,
            db=db,
        )
        return success_response(data={"items": orders, "total": len(orders)})
    except Exception as e:
        logger.error(f"获取可接订单列表失败: {e}")
        return error_response(4001, str(e))


@router.post("/delivery/orders/{order_id}/accept", summary="接单")
async def accept_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    配送员接单。

    创建配送记录，订单状态从 ready_pickup 变更为 delivering。
    同一订单只能被一个配送员接单。

    接单成功后通过 WebSocket 推送订单状态变更通知。
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        delivery_order = delivery_service.accept_order(
            delivery_person_id=delivery_person_id,
            order_id=order_id,
            db=db,
        )

        order = delivery_order.order
        delivery_person = delivery_order.delivery_person

        # 构造返回数据
        result = {
            "id": delivery_order.id,
            "order_id": delivery_order.order_id,
            "delivery_person_id": delivery_order.delivery_person_id,
            "status": delivery_order.status,
            "assigned_at": delivery_order.assigned_at.isoformat() if delivery_order.assigned_at else None,
            "order": {
                "id": order.id if order else None,
                "order_no": order.order_no if order else "",
                "order_status": order.order_status if order else "",
            },
        }

        # WebSocket 推送订单状态变更
        await _notify_order_update(request, order_id, {
            "type": "order_accepted",
            "order_id": order_id,
            "newStatus": order.order_status if order else "confirmed",
            "order_status": order.order_status if order else "confirmed",
            "delivery_status": delivery_order.status,
            "delivery": {
                "name": delivery_person.real_name if delivery_person else "",
                "phone": delivery_person.phone if delivery_person else "",
                "status": delivery_order.status,
            },
        })

        # WebSocket 推送新消息通知（群聊）
        dp_name = delivery_person.nickname or delivery_person.real_name if delivery_person else f"配送员{delivery_person_id}"
        await _notify_new_message(request, order_id,
            content=f"🛵 {dp_name}已接单，正在前往商家取餐。如有问题可在此联系配送员。",
            sender_name=dp_name, sender_role="delivery")

        return success_response(data=result, message="接单成功")

    except ValueError as e:
        return error_response(4002, str(e))
    except Exception as e:
        logger.error(f"接单失败: {e}")
        return error_response(5000, f"接单失败: {str(e)}")


@router.post("/delivery/orders/{order_id}/pickup", summary="确认取餐")
async def pickup_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    配送员确认已到店取餐。

    配送记录状态变更为 picked_up，记录取餐时间。
    取餐成功后通过 WebSocket 推送通知。
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        delivery_order = delivery_service.pickup_order(
            delivery_person_id=delivery_person_id,
            order_id=order_id,
            db=db,
        )

        result = {
            "id": delivery_order.id,
            "order_id": delivery_order.order_id,
            "delivery_person_id": delivery_order.delivery_person_id,
            "status": delivery_order.status,
            "picked_up_at": delivery_order.picked_up_at.isoformat() if delivery_order.picked_up_at else None,
        }

        # WebSocket 推送
        dp = delivery_order.delivery_person
        await _notify_order_update(request, order_id, {
            "type": "order_picked_up",
            "order_id": order_id,
            "newStatus": "delivering",
            "delivery_status": delivery_order.status,
            "delivery": {
                "name": dp.real_name if dp else "",
                "phone": dp.phone if dp else "",
                "status": delivery_order.status,
            },
            "picked_up_at": delivery_order.picked_up_at.isoformat() if delivery_order.picked_up_at else None,
        })

        # WebSocket 推送新消息通知（群聊）
        dp_name = dp.nickname or dp.real_name if dp else f"配送员{delivery_person_id}"
        await _notify_new_message(request, order_id,
            content=f"✅ {dp_name}已取餐，正在为您配送中。",
            sender_name=dp_name, sender_role="delivery")

        return success_response(data=result, message="取餐确认成功")

    except ValueError as e:
        return error_response(4002, str(e))
    except Exception as e:
        logger.error(f"确认取餐失败: {e}")
        return error_response(5000, f"确认取餐失败: {str(e)}")


@router.post("/delivery/orders/{order_id}/deliver", summary="确认送达")
async def deliver_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    配送员确认已送达。

    配送记录状态变更为 delivered，订单状态变更为 delivered，
    记录送达时间，配送员完成单数 +1。

    送达成功后通过 WebSocket 推送通知。
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        delivery_order = delivery_service.deliver_order(
            delivery_person_id=delivery_person_id,
            order_id=order_id,
            db=db,
        )

        result = {
            "id": delivery_order.id,
            "order_id": delivery_order.order_id,
            "delivery_person_id": delivery_order.delivery_person_id,
            "status": delivery_order.status,
            "delivered_at": delivery_order.delivered_at.isoformat() if delivery_order.delivered_at else None,
        }

        # WebSocket 推送订单已送达
        dp = delivery_order.delivery_person
        await _notify_order_update(request, order_id, {
            "type": "order_delivered",
            "order_id": order_id,
            "newStatus": "delivered",
            "delivery_status": delivery_order.status,
            "delivery": {
                "name": dp.real_name if dp else "",
                "phone": dp.phone if dp else "",
                "status": delivery_order.status,
            },
            "delivered_at": delivery_order.delivered_at.isoformat() if delivery_order.delivered_at else None,
        })

        # WebSocket 推送新消息通知（群聊）
        dp_name = dp.nickname or dp.real_name if dp else f"配送员{delivery_person_id}"
        await _notify_new_message(request, order_id,
            content=f"🏁 {dp_name}已送达，请确认收货。如有问题可联系配送员。",
            sender_name=dp_name, sender_role="delivery")

        return success_response(data=result, message="送达确认成功")

    except ValueError as e:
        return error_response(4002, str(e))
    except Exception as e:
        logger.error(f"确认送达失败: {e}")
        return error_response(5000, f"确认送达失败: {str(e)}")


@router.put("/delivery/me/location", summary="更新实时位置")
async def update_location(
    location: LocationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    配送员上报实时经纬度。

    位置更新后，系统将自动通过 WebSocket 推送给正在追踪该配送员订单的用户。
    建议配送员端每 10~15 秒上报一次位置。
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        delivery_person = delivery_service.update_location(
            delivery_person_id=delivery_person_id,
            lat=location.lat,
            lng=location.lng,
            db=db,
        )

        # WebSocket 推送位置更新给所有追踪该配送员订单的用户
        # 查找该配送员当前正在配送中的订单，逐个推送
        active_deliveries = (
            db.query(DeliveryOrder)
            .filter(
                DeliveryOrder.delivery_person_id == delivery_person_id,
                DeliveryOrder.status.in_(["assigned", "picked_up"]),
            )
            .all()
        )

        for delivery in active_deliveries:
            await _notify_location_update(request, delivery.order_id, {
                "order_id": delivery.order_id,
                "delivery_person_id": delivery_person_id,
                "name": delivery_person.real_name,
                "latitude": float(delivery_person.current_lat) if delivery_person.current_lat else None,
                "longitude": float(delivery_person.current_lng) if delivery_person.current_lng else None,
                "delivery_status": delivery.status,
                "updated_at": delivery_person.updated_at.isoformat() if delivery_person.updated_at else None,
            })

        return success_response(data={
            "delivery_person_id": delivery_person_id,
            "latitude": float(delivery_person.current_lat) if delivery_person.current_lat else None,
            "longitude": float(delivery_person.current_lng) if delivery_person.current_lng else None,
        }, message="位置已更新")

    except ValueError as e:
        return error_response(4002, str(e))
    except Exception as e:
        logger.error(f"更新位置失败: {e}")
        return error_response(5000, f"更新位置失败: {str(e)}")


@router.get("/delivery/me/orders", summary="我的配送订单")
async def get_my_delivery_orders(
    status: Optional[str] = Query(None, description="配送状态筛选: assigned / picked_up / delivered"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=50, description="每页条数"),
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    获取当前配送员的配送订单列表，支持状态筛选和分页。

    状态说明：
    - assigned: 已接单，待取餐
    - picked_up: 已取餐，配送中
    - delivered: 已送达
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        items, total = delivery_service.get_delivery_orders(
            delivery_person_id=delivery_person_id,
            status_filter=status,
            page=page,
            size=size,
            db=db,
        )
        return paginated_response(items=items, total=total, page=page, size=size)
    except Exception as e:
        logger.error(f"获取配送订单列表失败: {e}")
        return error_response(5000, str(e))


@router.get("/delivery/me/statistics", summary="配送统计")
async def get_my_statistics(
    db: Session = Depends(get_db),
    current_delivery: dict = Depends(get_current_delivery),
):
    """
    获取当前配送员的统计数据，包括：
    - 今日接单数
    - 今日完成数
    - 累计完成数
    - 今日收入
    - 平均评分
    """
    try:
        delivery_person_id = int(current_delivery["sub"])
        stats = delivery_service.get_delivery_statistics(
            delivery_person_id=delivery_person_id,
            db=db,
        )
        return success_response(data=stats)
    except ValueError as e:
        return error_response(4002, str(e))
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        return error_response(5000, str(e))


# ──────────────────────────── 配送员更新个人信息 ────────────────────────────


class DeliveryProfileUpdate(BaseModel):
    """配送员个人信息更新请求"""
    nickname: str | None = Field(None, max_length=50, description="配送员昵称")
    avatar_url: str | None = Field(None, max_length=500, description="头像URL")


@router.put("/delivery/me", summary="更新配送员个人信息")
def update_delivery_profile(
    req: DeliveryProfileUpdate,
    current_delivery: dict = Depends(get_current_delivery),
    db: Session = Depends(get_db),
):
    """更新当前登录配送员的昵称和头像"""
    delivery_person_id = int(current_delivery["sub"])
    dp = db.query(DeliveryPersonnel).filter(DeliveryPersonnel.id == delivery_person_id).first()
    if not dp:
        return error_response(4002, "配送员不存在")

    if req.nickname is not None:
        dp.nickname = req.nickname
    if req.avatar_url is not None:
        dp.avatar_url = req.avatar_url

    db.commit()
    db.refresh(dp)

    return success_response(
        data={
            "id": dp.id,
            "phone": dp.phone,
            "real_name": dp.real_name,
            "nickname": dp.nickname,
            "avatar_url": dp.avatar_url,
        },
        message="个人信息已更新",
    )
