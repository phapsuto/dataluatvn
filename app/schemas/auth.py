from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., example="phapsuto@gmail.com")
    password: str = Field(..., example="••••••••")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    expires_in_hours: int


class UserInfo(BaseModel):
    email: str


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, example="My App Key")


class ApiKeyResponse(BaseModel):
    id: int
    key_value: str
    name: str
    created_by: str
    created_at: str
    last_used_at: Optional[str] = None
    is_active: bool
    request_count: int


class ApiKeyCreated(BaseModel):
    id: int
    key_value: str
    name: str
    created_by: str
    created_at: str
    message: str = "API Key đã tạo thành công. Hãy lưu lại key này — bạn sẽ không thể xem lại toàn bộ key sau này."
