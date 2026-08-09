"""
地理计算工具模块
提供经纬度距离计算（Haversine 公式）、范围判断、距离格式化等功能。
"""

from math import asin, cos, radians, sin, sqrt


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    使用 Haversine 公式计算地球表面两点之间的大圆距离。

    Haversine 公式：
        a = sin²(Δlat/2) + cos(lat1) * cos(lat2) * sin²(Δlng/2)
        c = 2 * atan2(√a, √(1-a))
        d = R * c

    Args:
        lat1: 第一个点的纬度（度）
        lng1: 第一个点的经度（度）
        lat2: 第二个点的纬度（度）
        lng2: 第二个点的经度（度）

    Returns:
        两点之间的距离，单位为米（float）

    Example:
        >>> haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
        1068700.0  # 北京到上海约 1068.7 km
    """
    # 地球平均半径（米）
    EARTH_RADIUS_METERS = 6371000.0

    # 将角度转为弧度
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)

    # Haversine 公式
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    c = 2 * asin(sqrt(a))

    return EARTH_RADIUS_METERS * c


def is_within_radius(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
    radius_meters: float,
) -> bool:
    """
    判断两点是否在指定半径范围内。

    常用于配送范围校验：判断商家是否在用户指定范围内，
    或者配送员是否在可接单范围内。

    Args:
        lat1: 第一个点的纬度
        lng1: 第一个点的经度
        lat2: 第二个点的纬度
        lng2: 第二个点的经度
        radius_meters: 半径阈值（米）

    Returns:
        True 表示两点距离 <= radius_meters，否则 False

    Example:
        >>> is_within_radius(39.90, 116.40, 39.91, 116.41, 3000)
        True  # 两点距离约 1.4km，在 3km 范围内
    """
    distance = haversine_distance(lat1, lng1, lat2, lng2)
    return distance <= radius_meters


def format_distance(meters: float) -> str:
    """
    将距离（米）格式化为人类可读的字符串。

    格式规则：
        - < 1000m: 显示为 "500m"
        - >= 1000m: 显示为 "1.2km"，保留一位小数

    Args:
        meters: 距离，单位为米

    Returns:
        格式化后的距离字符串

    Example:
        >>> format_distance(500)
        "500m"
        >>> format_distance(1234)
        "1.2km"
        >>> format_distance(10800)
        "10.8km"
    """
    if meters < 1000:
        return f"{int(meters)}m"
    else:
        km = meters / 1000.0
        return f"{km:.1f}km"
