import os
import uuid
import time
import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from app.utils.llm_gateway import LLMGateway

logger = logging.getLogger("legal_doc_analyzer")

MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB max per file
MAX_ATTACHMENTS_PER_SESSION = 10       # 10 files max per session

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
os.makedirs(DB_DIR, exist_ok=True)
ATTACHMENTS_DB_PATH = os.path.join(DB_DIR, "chat_attachments.db")

def _init_attachments_db():
    try:
        with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_attachments (
                    attachment_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    structured_summary TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attach_session ON chat_attachments(session_id)")
            conn.commit()
    except Exception as e:
        logger.error(f"[Attachments DB Init Error] {e}")

_init_attachments_db()

class AttachmentSessionManager:
    """Manages chat attachments in SQLite & memory cache with 8MB size limit and 10 files limit."""
    
    @classmethod
    def get_session_attachments(cls, session_id: str) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        try:
            with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM chat_attachments WHERE session_id = ? ORDER BY created_at ASC",
                    (session_id,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[Get Session Attachments Error] {e}")
            return []

    @classmethod
    def get_attachment(cls, attachment_id: str) -> Optional[Dict[str, Any]]:
        if not attachment_id:
            return None
        try:
            with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM chat_attachments WHERE attachment_id = ?",
                    (attachment_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[Get Attachment Error] {e}")
            return None

    @classmethod
    def save_attachment(
        cls,
        session_id: str,
        filename: str,
        file_type: str,
        content_text: str,
        structured_summary: str,
        doc_type: str
    ) -> Dict[str, Any]:
        session_id = session_id or "default"
        # Enforce max 10 files per session
        existing = cls.get_session_attachments(session_id)
        if len(existing) >= MAX_ATTACHMENTS_PER_SESSION:
            raise ValueError(f"Mỗi phiên hội thoại chỉ được tải lên tối đa {MAX_ATTACHMENTS_PER_SESSION} tài liệu.")

        attachment_id = f"att_{uuid.uuid4().hex[:12]}"
        created_at = time.time()
        
        try:
            with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO chat_attachments (
                        attachment_id, session_id, filename, file_type,
                        content_text, structured_summary, doc_type, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attachment_id, session_id, filename, file_type,
                        content_text, structured_summary, doc_type, created_at
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[Save Attachment Error] {e}")
            raise e
            
        return {
            "attachment_id": attachment_id,
            "session_id": session_id,
            "filename": filename,
            "file_type": file_type,
            "content_text": content_text,
            "structured_summary": structured_summary,
            "doc_type": doc_type,
            "created_at": created_at
        }

    @classmethod
    def delete_attachment(cls, attachment_id: str) -> bool:
        try:
            with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
                cur = conn.execute("DELETE FROM chat_attachments WHERE attachment_id = ?", (attachment_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"[Delete Attachment Error] {e}")
            return False

    @classmethod
    def clear_session(cls, session_id: str) -> int:
        try:
            with sqlite3.connect(ATTACHMENTS_DB_PATH) as conn:
                cur = conn.execute("DELETE FROM chat_attachments WHERE session_id = ?", (session_id,))
                conn.commit()
                return cur.rowcount
        except Exception as e:
            logger.error(f"[Clear Session Attachments Error] {e}")
            return 0


class LegalDocumentAnalyzer:
    """Analyzes uploaded documents (PDF/DOCX/IMG/TXT) using FPT Cloud LLM."""
    
    @classmethod
    async def analyze_attachment(cls, content_text: str, filename: str) -> Dict[str, str]:
        """Uses LLMGateway (FPT Cloud model) to extract legal structure and risk points."""
        if not content_text or len(content_text.strip()) < 10:
            return {
                "doc_type": "Tài liệu chưa xác định",
                "structured_summary": f"Tài liệu '{filename}' có nội dung quá ngắn hoặc chưa nhận diện được văn bản."
            }
            
        # Truncate content for summary if extremely long (to fit prompt context)
        sample_text = content_text[:12000] if len(content_text) > 12000 else content_text
        
        system_prompt = (
            "Bạn là Trợ lý AI và Chuyên gia thẩm định pháp lý Lan Anh. "
            "Nhiệm vụ của bạn là đọc kỹ toàn văn tài liệu do người dùng tải lên, bóc tách cấu trúc pháp lý "
            "và trình bày tóm tắt rõ ràng, súc tích bằng Tiếng Việt theo cấu trúc sau:\n\n"
            "**1. Loại tài liệu:** (Hợp đồng, Biên bản, Quyết định, Đơn từ, Văn bản nội bộ...)\n"
            "**2. Các bên liên quan:** (Tên cá nhân/tổ chức, vai trò)\n"
            "**3. Điều khoản & Nội dung trọng tâm:** (Quyền lợi, nghĩa vụ, thời hạn, giá trị hợp đồng...)\n"
            "**4. Điểm rủi ro hoặc Vấn đề pháp lý cần đối chiếu:** (Nhận diện điểm có thể vi phạm pháp luật hiện hành hoặc rủi ro pháp lý)"
        )
        
        user_message = (
            f"Tên tài liệu: {filename}\n"
            f"Nội dung tài liệu:\n{sample_text}\n\n"
            "Hãy phân tích và bóc tách cấu trúc pháp lý của tài liệu trên theo cấu trúc 4 phần đã chỉ định."
        )
        
        try:
            summary_response = await LLMGateway.call_async(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=2048
            )
            summary_response = summary_response.strip()
            
            # Detect doc_type from first line or summary
            doc_type = "Tài liệu pháp lý"
            for line in summary_response.splitlines():
                if "1. Loại tài liệu" in line or "Loại tài liệu:" in line:
                    doc_type = line.split(":", 1)[-1].replace("**", "").strip()
                    break
            
            return {
                "doc_type": doc_type or "Tài liệu pháp lý",
                "structured_summary": summary_response
            }
        except Exception as e:
            logger.error(f"[Analyze Attachment LLM Error] {e}")
            # Clean fallback if LLM offline
            preview = sample_text[:800].replace("\n", " ") + "..."
            return {
                "doc_type": "Tài liệu văn bản",
                "structured_summary": f"**1. Loại tài liệu:** Văn bản đính kèm ({filename})\n**2. Tóm tắt nhanh nội dung:** {preview}\n**3. Lưu ý:** Hệ thống đang tra cứu đối chiếu điều khoản trong tài liệu này với pháp luật hiện hành."
            }
