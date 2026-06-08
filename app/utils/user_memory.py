import os
import logging
from typing import Dict, Any, List

# Create logs directory if not exists
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("user_memory")

# Import FPT credentials from project config
try:
    from app.config import FPT_CLOUD_API_KEY
except ImportError:
    FPT_CLOUD_API_KEY = os.environ.get("FPT_CLOUD_API_KEY") or "sk-o38ypse9lSfaKaDOQ9O7STlEbfZZ0PBLmJ1v_dwlSmM="

# Config for Mem0 with local FAISS, SQLite, and local HF embedding model
MEM0_CONFIG = {
    "vector_store": {
        "provider": "faiss",
        "config": {
            "path": "./users_memory_faiss",
            "embedding_model_dims": 768
        }
    },
    "embedder": {
        "provider": "huggingface",
        "config": {
            "model": "bkai-foundation-models/vietnamese-bi-encoder",
            "embedding_dims": 768
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "openai_base_url": "https://mkp-api.fptcloud.com/v1",
            "api_key": FPT_CLOUD_API_KEY,
            "model": "gemma-4-31B-it",
            "temperature": 0.1,
            "max_tokens": 500
        }
    },
    "db_path": "users_memory.db"
}

# Global memory instance
_MEM0_INSTANCE = None
_FALLBACK_ACTIVE = False

def get_mem0_instance():
    """Lazily initializes and returns the Mem0 memory instance with safety fallback."""
    global _MEM0_INSTANCE, _FALLBACK_ACTIVE
    if _MEM0_INSTANCE is None and not _FALLBACK_ACTIVE:
        try:
            from mem0 import Memory
            # Lazy import torch to avoid conflicts on startup
            import torch
            _MEM0_INSTANCE = Memory.from_config(MEM0_CONFIG)
            logger.info("✅ Mem0 Long-term Memory initialized successfully with Local FAISS + SQLite.")
        except Exception as e:
            print(f"⚠️ Error initializing Mem0: {e}. Fallback to pure SQLite session logs.")
            logger.error(f"Failed to initialize Mem0: {e}. Activating fallback.")
            _FALLBACK_ACTIVE = True
    return _MEM0_INSTANCE

class LegalUserMemory:
    @staticmethod
    def save_interaction(user_id: str, query: str, response: str, citations: List[dict]):
        """
        Saves user query, AI summary, and referenced legal citations to long-term memory.
        """
        m = get_mem0_instance()
        metadata = {
            "citations": [c.get("so_ky_hieu") or c.get("title") for c in citations if c],
            "doc_ids": [c.get("id") for c in citations if c]
        }
        
        # Format a clean textual description of the interaction
        interaction_text = f"Người dùng hỏi: '{query}'. Hệ thống tư vấn pháp luật và trích dẫn các tài liệu: {metadata['citations']}."
        
        if m and not _FALLBACK_ACTIVE:
            try:
                # Add to Mem0 (automatically extracts facts using Gemma LLM and embeds with local model)
                m.add(interaction_text, user_id=user_id, metadata=metadata)
            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.error(f"Error saving to Mem0: {e}")
                print(f"⚠️ Mem0 save error: {e}")
        else:
            # Fallback: log to a clean local file/database
            logger.info(f"[Fallback Memory Log] User: {user_id} | Query: {query} | Citations: {metadata['citations']}")

    @staticmethod
    def get_relevant_memories(user_id: str, current_query: str) -> str:
        """
        Retrieves top relevant memories from the user's history matching the current query.
        Returns a formatted string context.
        """
        m = get_mem0_instance()
        if not m or _FALLBACK_ACTIVE:
            return ""
            
        try:
            # Search relevant memories using local vector search with filters
            results = m.search(current_query, filters={"user_id": user_id}, limit=3)
            if not results:
                return ""
            
            if isinstance(results, dict) and "results" in results:
                results = results["results"]
                
            memories = []
            for item in results:
                text = ""
                if isinstance(item, dict):
                    text = item.get("memory") or item.get("text")
                elif hasattr(item, "memory"):
                    text = item.memory
                elif hasattr(item, "text"):
                    text = item.text
                elif isinstance(item, str):
                    text = item
                    
                if text:
                    memories.append(f"- {text}")
                    
            if memories:
                return "LỊCH SỬ TƯ VẤN VÀ THÓI QUEN CỦA NGƯỜI DÙNG:\n" + "\n".join(memories)
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error searching memories: {e}")
            
        return ""

    @staticmethod
    def get_user_profile(user_id: str) -> dict:
        """
        Aggregates and returns user profile, interests, and most searched legal documents.
        """
        m = get_mem0_instance()
        profile = {
            "user_id": user_id,
            "frequent_topics": [],
            "referenced_docs": [],
            "memories_count": 0
        }
        
        if not m or _FALLBACK_ACTIVE:
            return profile
            
        try:
            memories = m.get_all(filters={"user_id": user_id})
            if not memories:
                return profile
                
            if isinstance(memories, dict) and "results" in memories:
                memories = memories["results"]
                
            profile["memories_count"] = len(memories)
            
            docs = set()
            for item in memories:
                meta = {}
                if isinstance(item, dict):
                    meta = item.get("metadata") or {}
                elif hasattr(item, "metadata"):
                    meta = item.metadata or {}
                elif hasattr(item, "get"):
                    meta = item.get("metadata") or {}
                    
                citations = meta.get("citations") or [] if isinstance(meta, dict) else []
                for c in citations:
                    docs.add(c)
                    
            profile["referenced_docs"] = list(docs)[:5]
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error getting user profile: {e}")
            
        return profile
