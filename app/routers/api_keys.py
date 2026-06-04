import secrets
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_jwt
from app.database import get_admin_db
from app.schemas.auth import ApiKeyCreate, ApiKeyResponse, ApiKeyCreated

router = APIRouter(tags=["🔑 API Keys"])


@router.get("/admin/api-keys", response_model=List[ApiKeyResponse], summary="Danh sách API Keys")
def list_api_keys(user=Depends(require_jwt)):
    """Lấy danh sách tất cả API Keys (yêu cầu đăng nhập)."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        d["is_active"] = bool(d["is_active"])
        results.append(d)
    return results


@router.post("/admin/api-keys", response_model=ApiKeyCreated, summary="Tạo API Key mới")
def create_api_key(body: ApiKeyCreate, user=Depends(require_jwt)):
    """
    Tạo một API Key mới. Key có dạng `dlvn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
    **Lưu ý:** Hãy lưu key ngay sau khi tạo.
    """
    key_value = f"dlvn_{secrets.token_hex(24)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO api_keys (key_value, name, created_by, created_at) VALUES (?, ?, ?, ?)",
        (key_value, body.name.strip(), user["sub"], now),
    )
    conn.commit()
    key_id = cursor.lastrowid
    conn.close()

    return {
        "id": key_id,
        "key_value": key_value,
        "name": body.name.strip(),
        "created_by": user["sub"],
        "created_at": now,
    }


@router.put("/admin/api-keys/{key_id}/toggle", summary="Bật/tắt API Key")
def toggle_api_key(key_id: int, user=Depends(require_jwt)):
    """Bật hoặc tắt trạng thái hoạt động của một API Key."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key.")

    new_status = 0 if row["is_active"] else 1
    cursor.execute("UPDATE api_keys SET is_active = ? WHERE id = ?", (new_status, key_id))
    conn.commit()
    conn.close()

    return {"message": "Đã cập nhật trạng thái", "is_active": bool(new_status)}


@router.delete("/admin/api-keys/{key_id}", summary="Xóa API Key")
def delete_api_key(key_id: int, user=Depends(require_jwt)):
    """Xóa vĩnh viễn một API Key."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key.")

    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()

    return {"message": "Đã xóa API Key thành công."}
