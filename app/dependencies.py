"""
依赖注入模块
提供 FastAPI 依赖注入函数，包括数据库会话、当前用户/商家/配送员/管理员获取，以及角色权限检查。
"""

from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.config import settings

# 临时使用 HTTPBearer，后续替换为数据库会话
security_scheme = HTTPBearer()


# ==================== 数据库会话 ====================
def get_db() -> Generator[Session, None, None]:
    """
    数据库会话生成器。
    在请求开始时创建数据库会话，请求结束后自动关闭会话并归还到连接池。

    使用方式（FastAPI 路由中）:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    from app.models.base import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== JWT Token 解析辅助函数 ====================
def _decode_token_and_get_user(
    token: str,
    expected_role: Optional[str] = None,
) -> dict:
    """
    解析 JWT Token 并返回 payload 中的用户信息。
    可通过 expected_role 约束必须为特定角色。

    Args:
        token: JWT token 字符串
        expected_role: 期望的角色类型 (user/merchant/delivery/admin)

    Returns:
        payload 字典，包含 sub, role, user_id 等字段

    Raises:
        HTTPException 401: token 无效或过期
        HTTPException 403: 角色不匹配
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
        )

    user_id = payload.get("sub")
    role = payload.get("role")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证凭证中缺少用户标识",
        )

    if expected_role is not None and role != expected_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要 {expected_role} 角色",
        )

    return payload


# ==================== 当前用户依赖注入 ====================
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    从请求头的 Bearer Token 中解析当前普通用户信息。
    要求 token 中 role 为 'user'。
    """
    return _decode_token_and_get_user(credentials.credentials, expected_role="user")


async def get_current_merchant(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    从请求头的 Bearer Token 中解析当前商家信息。
    要求 token 中 role 为 'merchant'。
    """
    return _decode_token_and_get_user(credentials.credentials, expected_role="merchant")


async def get_current_delivery(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    从请求头的 Bearer Token 中解析当前配送员信息。
    要求 token 中 role 为 'delivery'。
    """
    return _decode_token_and_get_user(credentials.credentials, expected_role="delivery")


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    从请求头的 Bearer Token 中解析当前管理员信息。
    要求 token 中 role 为 'admin'。
    """
    return _decode_token_and_get_user(credentials.credentials, expected_role="admin")


# ==================== 基于角色的权限检查类 ====================
class RoleChecker:
    """
    基于角色的权限检查器。
    用于 FastAPI 路由的 dependencies 参数中，限制接口只允许指定角色访问。

    使用示例:
        @router.get("/admin/dashboard", dependencies=[Depends(RoleChecker(["admin"]))])
        async def admin_dashboard():
            ...

        @router.post("/merchant/menu", dependencies=[Depends(RoleChecker(["merchant", "admin"]))])
        async def add_menu_item():
            ...
    """

    def __init__(self, allowed_roles: list[str]):
        """
        Args:
            allowed_roles: 允许访问的角色列表，例如 ["admin", "merchant"]
        """
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    ) -> dict:
        """
        校验当前用户角色是否在允许列表中。
        """
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭证",
            )

        role = payload.get("role")

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证凭证中缺少角色信息",
            )

        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，允许的角色: {', '.join(self.allowed_roles)}",
            )

        return payload
