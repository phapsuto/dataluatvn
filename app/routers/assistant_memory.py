import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Path, Query, HTTPException

from app.dependencies import require_api_key
from app.database import get_memory_db

router = APIRouter(prefix="/assistant", tags=["🤖 Trợ lý ảo - Bộ nhớ & Ngữ cảnh"])


# ╔══════════════════════════════════════════════════════════════╗
# ║                      SCHEMAS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class UserProfileCreate(BaseModel):
    user_id: str = Field(..., description="ID định danh duy nhất của người dùng")
    full_name: Optional[str] = Field(None, description="Họ và tên")
    location: Optional[str] = Field(None, description="Địa phương (ví dụ: TP.HCM, Hà Nội) để lọc luật địa phương")
    job_title: Optional[str] = Field(None, description="Nghề nghiệp/Chức danh")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Thông tin mở rộng dạng JSON")

class UserProfileResponse(BaseModel):
    user_id: str
    full_name: Optional[str]
    location: Optional[str]
    job_title: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: str

class CaseFileCreate(BaseModel):
    case_id: str = Field(..., description="ID vụ việc")
    user_id: str = Field(..., description="ID người dùng sở hữu vụ việc")
    title: str = Field(..., description="Tiêu đề vụ việc")
    summary: Optional[str] = Field(None, description="Tóm tắt nội dung vụ việc")
    facts: Optional[str] = Field(None, description="Các tình tiết pháp lý cốt lõi")
    status: Optional[str] = Field("active", description="Trạng thái vụ việc: active, closed")

class CaseFileResponse(BaseModel):
    case_id: str
    user_id: str
    title: str
    summary: Optional[str]
    facts: Optional[str]
    status: str
    created_at: str
    updated_at: str

class ChatSessionCreate(BaseModel):
    session_id: str = Field(..., description="ID phiên hội thoại")
    user_id: str = Field(..., description="ID người dùng")
    case_id: Optional[str] = Field(None, description="ID vụ việc liên kết (nếu có)")
    title: Optional[str] = Field(None, description="Tiêu đề cuộc hội thoại")

class ChatSessionResponse(BaseModel):
    session_id: str
    user_id: str
    case_id: Optional[str]
    title: Optional[str]
    created_at: str

class ChatMessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$", description="Vai trò: user, assistant, system")
    content: str = Field(..., description="Nội dung tin nhắn")

class ChatMessageResponse(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    created_at: str

class SessionContextResponse(BaseModel):
    session: ChatSessionResponse
    user_profile: Optional[UserProfileResponse]
    case_file: Optional[CaseFileResponse]
    chat_history: List[ChatMessageResponse]


# ╔══════════════════════════════════════════════════════════════╗
# ║                      ROUTERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/profile", response_model=UserProfileResponse, summary="Tạo hoặc cập nhật thông tin người dùng")
def upsert_user_profile(profile: UserProfileCreate, _key=Depends(require_api_key)):
    """Tạo mới hoặc cập nhật hồ sơ người dùng. Thông tin này giúp AI định hình vị trí địa lý của khách hàng để áp dụng luật địa phương."""
    conn = get_memory_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    meta_json = json.dumps(profile.metadata) if profile.metadata else "{}"
    
    try:
        # Check if exists
        cursor.execute("SELECT created_at FROM user_profiles WHERE user_id = ?", (profile.user_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE user_profiles 
                SET full_name = ?, location = ?, job_title = ?, metadata = ?
                WHERE user_id = ?
            """, (profile.full_name, profile.location, profile.job_title, meta_json, profile.user_id))
            created_at = row["created_at"]
        else:
            cursor.execute("""
                INSERT INTO user_profiles (user_id, full_name, location, job_title, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (profile.user_id, profile.full_name, profile.location, profile.job_title, meta_json, now_iso))
            created_at = now_iso
            
        conn.commit()
        conn.close()
        
        return {
            "user_id": profile.user_id,
            "full_name": profile.full_name,
            "location": profile.location,
            "job_title": profile.job_title,
            "metadata": profile.metadata or {},
            "created_at": created_at
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Lỗi cơ sở dữ liệu: {str(e)}")


@router.get("/profile/{user_id}", response_model=UserProfileResponse, summary="Lấy hồ sơ người dùng")
def get_user_profile(user_id: str = Path(..., description="ID người dùng"), _key=Depends(require_api_key)):
    conn = get_memory_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ người dùng.")
        
    doc = dict(row)
    doc["metadata"] = json.loads(doc["metadata"]) if doc.get("metadata") else {}
    return doc


@router.post("/cases", response_model=CaseFileResponse, summary="Tạo hoặc cập nhật hồ sơ vụ việc")
def upsert_case_file(case: CaseFileCreate, _key=Depends(require_api_key)):
    """Lưu trữ hồ sơ vụ việc pháp lý đang thụ lý. Trích xuất các tình tiết cốt lõi (facts) giúp AI RAG bám sát ngữ cảnh thực tế."""
    conn = get_memory_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Kiểm tra xem user_id có tồn tại không
    cursor.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (case.user_id,))
    if not cursor.fetchone():
        # Tự động tạo profile trống nếu chưa tồn tại
        cursor.execute("""
            INSERT INTO user_profiles (user_id, created_at)
            VALUES (?, ?)
        """, (case.user_id, now_iso))
        
    try:
        cursor.execute("SELECT created_at FROM case_files WHERE case_id = ?", (case.case_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE case_files 
                SET title = ?, summary = ?, facts = ?, status = ?, updated_at = ?
                WHERE case_id = ?
            """, (case.title, case.summary, case.facts, case.status, now_iso, case.case_id))
            created_at = row["created_at"]
        else:
            cursor.execute("""
                INSERT INTO case_files (case_id, user_id, title, summary, facts, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (case.case_id, case.user_id, case.title, case.summary, case.facts, case.status, now_iso, now_iso))
            created_at = now_iso
            
        conn.commit()
        conn.close()
        
        return {
            "case_id": case.case_id,
            "user_id": case.user_id,
            "title": case.title,
            "summary": case.summary,
            "facts": case.facts,
            "status": case.status or "active",
            "created_at": created_at,
            "updated_at": now_iso
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Lỗi lưu trữ hồ sơ: {str(e)}")


@router.get("/cases/{case_id}", response_model=CaseFileResponse, summary="Lấy chi tiết hồ sơ vụ việc")
def get_case_file(case_id: str = Path(..., description="ID vụ việc"), _key=Depends(require_api_key)):
    conn = get_memory_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM case_files WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ vụ việc.")
    return dict(row)


@router.get("/cases/user/{user_id}", response_model=List[CaseFileResponse], summary="Lấy danh sách vụ việc của người dùng")
def get_user_cases(user_id: str = Path(..., description="ID người dùng"), _key=Depends(require_api_key)):
    conn = get_memory_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM case_files WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.post("/sessions", response_model=ChatSessionResponse, summary="Tạo phiên hội thoại mới")
def create_chat_session(session: ChatSessionCreate, _key=Depends(require_api_key)):
    """Khởi tạo một phiên hội thoại độc lập cho trợ lý ảo, có thể liên kết trực tiếp với hồ sơ vụ việc."""
    conn = get_memory_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Kiểm tra xem user_id có tồn tại không
    cursor.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (session.user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO user_profiles (user_id, created_at) VALUES (?, ?)", (session.user_id, now_iso))
        
    # Kiểm tra case_id nếu có
    if session.case_id:
        cursor.execute("SELECT 1 FROM case_files WHERE case_id = ?", (session.case_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Mã hồ sơ vụ việc liên kết không tồn tại.")
            
    try:
        cursor.execute("SELECT created_at FROM chat_sessions WHERE session_id = ?", (session.session_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE chat_sessions SET case_id = ?, title = ? WHERE session_id = ?
            """, (session.case_id, session.title, session.session_id))
            created_at = row["created_at"]
        else:
            cursor.execute("""
                INSERT INTO chat_sessions (session_id, user_id, case_id, title, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (session.session_id, session.user_id, session.case_id, session.title, now_iso))
            created_at = now_iso
            
        conn.commit()
        conn.close()
        
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "case_id": session.case_id,
            "title": session.title or "Hội thoại pháp luật",
            "created_at": created_at
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Lỗi khởi tạo phiên chat: {str(e)}")


@router.post("/sessions/{session_id}/message", response_model=ChatMessageResponse, summary="Thêm tin nhắn vào phiên hội thoại")
def add_chat_message(
    message: ChatMessageCreate,
    session_id: str = Path(..., description="ID phiên hội thoại"),
    _key=Depends(require_api_key)
):
    """Ghi nhận tin nhắn mới (của người dùng hoặc của trợ lý AI) để củng cố ngữ cảnh trao đổi liên tục."""
    conn = get_memory_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Kiểm tra xem session_id có tồn tại không
    cursor.execute("SELECT 1 FROM chat_sessions WHERE session_id = ?", (session_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại yêu cầu.")
        
    try:
        cursor.execute("""
            INSERT INTO chat_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, message.role, message.content, now_iso))
        
        msg_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {
            "message_id": msg_id,
            "session_id": session_id,
            "role": message.role,
            "content": message.content,
            "created_at": now_iso
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Lỗi lưu tin nhắn: {str(e)}")


@router.get("/sessions/{session_id}/context", response_model=SessionContextResponse, summary="Lấy toàn bộ ngữ cảnh phục vụ RAG")
def get_session_context(
    session_id: str = Path(..., description="ID phiên hội thoại"),
    limit: int = Query(20, description="Giới hạn số lượng tin nhắn hội thoại gần nhất"),
    _key=Depends(require_api_key)
):
    """
    Trả về toàn bộ ngữ cảnh tích hợp của phiên hội thoại (Thông tin người dùng + Chi tiết vụ việc + Lịch sử chat gần nhất).
    Endpoint này dùng để nạp trực tiếp làm system prompt hoặc context cho LLM khi thực hiện RAG pháp lý.
    """
    conn = get_memory_db()
    cursor = conn.cursor()
    
    # 1. Lấy thông tin session
    cursor.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại yêu cầu.")
        
    session = dict(session_row)
    user_id = session["user_id"]
    case_id = session["case_id"]
    
    # 2. Lấy thông tin user profile
    user_profile = None
    if user_id:
        cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
        up_row = cursor.fetchone()
        if up_row:
            up_dict = dict(up_row)
            up_dict["metadata"] = json.loads(up_dict["metadata"]) if up_dict.get("metadata") else {}
            user_profile = up_dict
            
    # 3. Lấy thông tin hồ sơ vụ việc
    case_file = None
    if case_id:
        cursor.execute("SELECT * FROM case_files WHERE case_id = ?", (case_id,))
        cf_row = cursor.fetchone()
        if cf_row:
            case_file = dict(cf_row)
            
    # 4. Lấy lịch sử tin nhắn
    cursor.execute("""
        SELECT * FROM chat_messages 
        WHERE session_id = ? 
        ORDER BY message_id DESC 
        LIMIT ?
    """, (session_id, limit))
    # Đảo ngược lại để đúng thứ tự thời gian tăng dần
    chat_history = [dict(r) for r in cursor.fetchall()][::-1]
    
    conn.close()
    
    return {
        "session": session,
        "user_profile": user_profile,
        "case_file": case_file,
        "chat_history": chat_history
    }
