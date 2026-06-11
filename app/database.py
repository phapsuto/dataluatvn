import os
import time
import sqlite3
from functools import wraps

from fastapi import HTTPException

from app.config import DB_NAME, CONTENT_DB, ADMIN_DB, MEMORY_DB


# ╔══════════════════════════════════════════════════════════════╗
# ║                   DATABASE CONNECTIONS                      ║
# ╚══════════════════════════════════════════════════════════════╝

def get_db_connection():
    """Connect to the main legal documents database (metadata only, ~300 MB)."""
    if not os.path.exists(DB_NAME):
        raise HTTPException(
            status_code=500,
            detail="Database file not found. Please run download_all_to_sqlite.py first.",
        )
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.create_function("lower", 1, lambda s: s.lower() if s is not None else None)
    conn.row_factory = sqlite3.Row
    # ── PRAGMA tối ưu RAM ──
    conn.execute("PRAGMA cache_size = -32000")   # 32 MB cache (thay vì mặc định hàng GB)
    conn.execute("PRAGMA mmap_size = 0")          # Tắt memory-mapped I/O
    conn.execute("PRAGMA journal_mode = WAL")     # Write-Ahead Logging cho concurrent reads
    conn.execute("PRAGMA synchronous = NORMAL")   # Cân bằng safety/performance
    conn.execute("PRAGMA temp_store = FILE")      # Temp tables lưu disk, không RAM
    return conn


def get_content_connection():
    """Connect to content_store.db (chỉ chứa content_html, ~3.3 GB).
    Chỉ mở khi cần lấy toàn văn 1 document cụ thể."""
    if not os.path.exists(CONTENT_DB):
        return None  # Fallback: content vẫn nằm trong DB chính
    conn = sqlite3.connect(CONTENT_DB, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -8000")    # 8 MB cache (chỉ đọc 1 row)
    conn.execute("PRAGMA mmap_size = 0")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA temp_store = FILE")
    return conn


def get_admin_db():
    """Connect to the admin database (API keys)."""
    conn = sqlite3.connect(ADMIN_DB, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_admin_db():
    """Initialize admin database with api_keys table."""
    conn = sqlite3.connect(ADMIN_DB, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_value TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            is_active INTEGER DEFAULT 1,
            request_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_value ON api_keys(key_value)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON api_keys(is_active)")
    cursor.execute("""
        INSERT OR IGNORE INTO api_keys (key_value, name, created_by, created_at, is_active)
        VALUES (?, ?, ?, ?, 1)
    """, ('dlvn_portal_default_key', 'Portal Default Key', 'system', time.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    print("✅ Admin database initialized")


# ╔══════════════════════════════════════════════════════════════╗
# ║                     CACHE DECORATOR                         ║
# ╚══════════════════════════════════════════════════════════════╝

def simple_ttl_cache(ttl_seconds: int):
    def decorator(func):
        cached_value = None
        last_update = 0
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal cached_value, last_update
            if time.time() - last_update > ttl_seconds:
                cached_value = func(*args, **kwargs)
                last_update = time.time()
            return cached_value
        return wrapper
    return decorator


# ╔══════════════════════════════════════════════════════════════╗
# ║                   MEMORY DATABASE (ASSISTANT)                ║
# ╚══════════════════════════════════════════════════════════════╝

def get_memory_db():
    """Connect to the user session and case memory database."""
    conn = sqlite3.connect(MEMORY_DB, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_memory_db():
    """Initialize user_session_memory.db tables for Assistant profiling & chat history."""
    conn = sqlite3.connect(MEMORY_DB, timeout=30.0)
    cursor = conn.cursor()
    
    # 1. Bảng User Profiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            full_name TEXT,
            location TEXT, -- Ví dụ: TP.HCM (để AI tự lọc luật địa phương)
            job_title TEXT,
            metadata TEXT, -- JSON string
            created_at TEXT NOT NULL
        )
    """)
    
    # 2. Bảng Case Files (Hồ sơ vụ việc pháp lý)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_files (
            case_id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT NOT NULL,
            summary TEXT, -- Tóm tắt vụ việc
            facts TEXT,   -- Các sự kiện pháp lý quan trọng
            status TEXT DEFAULT 'active', -- active, closed
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
        )
    """)
    
    # 3. Bảng Chat Sessions (Lịch sử hội thoại trợ lý ảo)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            case_id TEXT,
            title TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE,
            FOREIGN KEY (case_id) REFERENCES case_files(case_id) ON DELETE SET NULL
        )
    """)
    
    # 4. Bảng Chat Messages (Log chi tiết hội thoại)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL, -- user, assistant, system
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_user ON user_profiles(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_user ON case_files(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON chat_sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON chat_messages(session_id)")
    
    conn.commit()
    conn.close()
    print("✅ Memory database initialized")
