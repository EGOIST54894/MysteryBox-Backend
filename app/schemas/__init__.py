"""
Pydantic Schemas 包
统一导出所有请求/响应模型，方便外部引用。
"""

from app.schemas.auth import (
    SendSMSRequest,
    PhoneLoginRequest,
    PasswordLoginRequest,
    RegisterRequest,
    TokenResponse,
    RefreshTokenRequest,
)

from app.schemas.user import (
    UserResponse,
    UserUpdateRequest,
    AddressCreate,
    AddressUpdate,
    AddressResponse,
)

from app.schemas.mystery_box import (
    BoxCreate,
    BoxUpdate,
    BoxResponse,
    BoxListQuery,
)

from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
)

from app.schemas.review import (
    ReviewCreate,
    ReviewResponse,
)

__all__ = [
    # auth
    "SendSMSRequest",
    "PhoneLoginRequest",
    "PasswordLoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    # user
    "UserResponse",
    "UserUpdateRequest",
    "AddressCreate",
    "AddressUpdate",
    "AddressResponse",
    # mystery_box
    "BoxCreate",
    "BoxUpdate",
    "BoxResponse",
    "BoxListQuery",
    # order
    "OrderCreate",
    "OrderResponse",
    "OrderStatusUpdate",
    # review
    "ReviewCreate",
    "ReviewResponse",
]
