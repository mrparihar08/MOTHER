from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    body: str
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    next_cursor: Optional[str] = None
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class ReadAllResponse(BaseModel):
    updated_count: int


class PushPublicKeyResponse(BaseModel):
    public_key: str


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    device_name: Optional[str] = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class NotificationPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    in_app_enabled: bool
    push_enabled: bool
    category_settings: Dict[str, bool]
    updated_at: datetime


class NotificationPreferencesUpdate(BaseModel):
    in_app_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    category_settings: Optional[Dict[str, bool]] = None


class TestPushRequest(BaseModel):
    title: Optional[str] = "Test Push Notification"
    body: Optional[str] = "Web Push notifications are active and verified on Vitya AI!"
