import hashlib

from fastapi import APIRouter, Depends

from app.config import ACCOUNTS, JWT_EXPIRE_HOURS
from app.dependencies import require_jwt, create_jwt_token
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo
from fastapi import HTTPException

router = APIRouter(tags=["🔐 Authentication"])


@router.post("/auth/login", response_model=LoginResponse, summary="Đăng nhập")
def login(body: LoginRequest):
    """
    Đăng nhập bằng email và mật khẩu.
    Chỉ các tài khoản nội bộ được phép đăng nhập.
    Trả về JWT token dùng để quản lý API Keys.
    """
    email = body.email.strip().lower()
    password_hash = hashlib.sha256(body.password.encode()).hexdigest()

    expected_hash = ACCOUNTS.get(email)
    if not expected_hash or password_hash != expected_hash:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng.")

    token = create_jwt_token(email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": email,
        "expires_in_hours": JWT_EXPIRE_HOURS,
    }


@router.get("/auth/me", response_model=UserInfo, summary="Thông tin người dùng")
def get_current_user(user=Depends(require_jwt)):
    """Lấy thông tin tài khoản đang đăng nhập (yêu cầu JWT token)."""
    return {"email": user["sub"]}
