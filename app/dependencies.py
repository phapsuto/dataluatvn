from typing import Optional
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import HTTPException, Depends, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS, ACCOUNTS
from app.database import get_admin_db


# ╔══════════════════════════════════════════════════════════════╗
# ║                   SECURITY SCHEMES                          ║
# ╚══════════════════════════════════════════════════════════════╝

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ╔══════════════════════════════════════════════════════════════╗
# ║                     JWT HELPERS                             ║
# ╚══════════════════════════════════════════════════════════════╝

def create_jwt_token(email: str) -> str:
    """Create a JWT token for admin access."""
    payload = {
        "sub": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token đã hết hạn. Vui lòng đăng nhập lại.")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ.")


# ╔══════════════════════════════════════════════════════════════╗
# ║                 SECURITY DEPENDENCIES                       ║
# ╚══════════════════════════════════════════════════════════════╝

async def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Dependency: require valid JWT token (for admin endpoints)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập. Vui lòng đăng nhập tại /admin")
    return decode_jwt_token(credentials.credentials)


async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Depends(api_key_header_scheme),
    api_key_query: Optional[str] = Query(None, alias="api_key", include_in_schema=False),
):
    """Dependency: require valid API key OR admin JWT (for law data endpoints)."""
    key = x_api_key or api_key_query

    # 1. Try API key
    if key:
        conn = get_admin_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key_value = ? AND is_active = 1", (key,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=403, detail="API Key không hợp lệ hoặc đã bị vô hiệu hóa.")

        cursor.execute(
            "UPDATE api_keys SET last_used_at = ?, request_count = request_count + 1 WHERE key_value = ?",
            (datetime.now(timezone.utc).isoformat(), key),
        )
        conn.commit()
        conn.close()
        return dict(row)

    # 2. Try JWT (admin dashboard access)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("sub") in ACCOUNTS:
                return {"type": "admin", "email": payload["sub"]}
        except Exception:
            pass

    raise HTTPException(
        status_code=401,
        detail="Yêu cầu API Key. Vui lòng đăng nhập tại /admin để tạo API key.",
    )
