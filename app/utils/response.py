"""
统一响应格式模块
定义项目标准 API 响应结构，确保所有接口返回格式一致。
"""

from math import ceil
from typing import Any, Optional


def success_response(data: Any = None, message: str = "success") -> dict:
    """
    成功响应格式。

    Args:
        data: 响应数据，可以是 dict、list 或任意可序列化对象
        message: 提示消息，默认 "success"

    Returns:
        标准成功响应字典: {"code": 200, "message": ..., "data": ...}

    Example:
        >>> success_response({"id": 1, "name": "张三"})
        {"code": 200, "message": "success", "data": {"id": 1, "name": "张三"}}
    """
    return {
        "code": 200,
        "message": message,
        "data": data,
    }


def error_response(code: int, message: str) -> dict:
    """
    错误响应格式。

    Args:
        code: 业务错误码（非零值）
        message: 错误描述信息

    Returns:
        标准错误响应字典: {"code": ..., "message": ..., "data": None}

    Example:
        >>> error_response(1001, "用户不存在")
        {"code": 1001, "message": "用户不存在", "data": None}
    """
    return {
        "code": code,
        "message": message,
        "data": None,
    }


def paginated_response(
    items: list,
    total: int,
    page: int,
    size: int,
) -> dict:
    """
    分页响应格式。

    Args:
        items: 当前页数据列表
        total: 数据总条数
        page: 当前页码（从 1 开始）
        size: 每页条数

    Returns:
        标准分页响应字典，包含分页元信息

    Example:
        >>> paginated_response(items=[...], total=100, page=1, size=20)
        {
            "code": 200,
            "message": "success",
            "data": {
                "items": [...],
                "pagination": {
                    "total": 100,
                    "page": 1,
                    "size": 20,
                    "total_pages": 5
                }
            }
        }
    """
    total_pages = ceil(total / size) if total > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
                "total_pages": total_pages,
            },
        },
    }
