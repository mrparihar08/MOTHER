"""
Security & Token Models for Shared Microservices Mesh.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Role:
    USER = "user"
    ADMIN = "admin"
    PREMIUM = "premium"
    SERVICE = "service"


class Permission:
    READ_FINANCE = "finance:read"
    WRITE_FINANCE = "finance:write"
    CHAT = "chat:interact"
    DORA = "dora:access"
    PRESENTATION = "presentation:create"
    ADMIN = "admin:all"


class AuthenticatedUser(BaseModel):
    user_id: int
    email: str
    roles: List[str] = Field(default_factory=lambda: [Role.USER])
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = True
    token: Optional[str] = None

    def has_role(self, role: str) -> bool:
        return Role.ADMIN in self.roles or role in self.roles

    def has_permission(self, permission: str) -> bool:
        return (
            Role.ADMIN in self.roles
            or Permission.ADMIN in self.permissions
            or permission in self.permissions
        )


class TokenPayload(BaseModel):
    sub: str  # User ID as string
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=lambda: [Role.USER])
    permissions: List[str] = Field(default_factory=list)
    iss: Optional[str] = None
    aud: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None
