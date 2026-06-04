import os
import time
import sqlite3
from functools import wraps

from fastapi import HTTPException

from app.config import DB_NAME, CONTENT_DB, ADMIN_DB


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
