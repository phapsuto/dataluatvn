import os
import logging
from typing import List

os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("user_memory")

class LegalUserMemory:
    @staticmethod
    def save_interaction(user_id: str, query: str, response: str, citations: List[dict]):
        """
        [DEPRECATED] Chuyển sang dùng SQLite chat_messages trực tiếp trong chatbot.py
        Giữ lại hàm này để không bị lỗi code cũ.
        """
        metadata = {
            "citations": [c.get("so_ky_hieu") or c.get("title") for c in citations if c],
            "doc_ids": [c.get("id") for c in citations if c]
        }
        logger.info(f"[SQLite Memory Active] User: {user_id} | Query: {query} | Citations: {metadata['citations']}")

    @staticmethod
    def get_relevant_memories(user_id: str, current_query: str) -> str:
        """
        [DEPRECATED] Trả về rỗng do đã dùng _get_chat_history_text từ SQLite
        """
        return ""

    @staticmethod
    def get_user_profile(user_id: str) -> dict:
        """
        [DEPRECATED] Trả về dữ liệu trống
        """
        return {
            "user_id": user_id,
            "frequent_topics": [],
            "referenced_docs": [],
            "memories_count": 0
        }
