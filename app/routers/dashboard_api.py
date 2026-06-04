import os
import json
import time
import signal
import sqlite3
import subprocess

from fastapi import APIRouter, Query, Request, HTTPException

from app.config import DB_NAME, CONTENT_DB
from app.database import get_db_connection, get_content_connection

router = APIRouter(prefix="/api/dashboard", include_in_schema=False)

# Resolve project root (where server.py, scripts, and logs live)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global crawler process reference
_crawler_process = None


@router.get("/stats")
def dashboard_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE has_content = 1")
    with_content = c.fetchone()[0]
    without_content = total - with_content

    c.execute("SELECT loai_van_ban, COUNT(*) FROM documents GROUP BY loai_van_ban ORDER BY COUNT(*) DESC LIMIT 10")
    by_type = [{"name": r[0] or "Không xác định", "count": r[1]} for r in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM relationships")
    total_rels = c.fetchone()[0]

    try:
        c.execute("SELECT COUNT(*) FROM article_modifications")
        total_mods = c.fetchone()[0]
    except:
        total_mods = 0

    try:
        c.execute("SELECT COUNT(*) FROM documents_fts")
        fts_count = c.fetchone()[0]
    except:
        fts_count = 0

    try:
        c.execute("SELECT COUNT(*) FROM anle_documents")
        total_anle = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM anle_documents WHERE precedent_number IS NOT NULL AND precedent_number != ''")
        total_precedents = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM phapdien_articles")
        total_phapdien = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM phapdien_glossary")
        total_glossary = c.fetchone()[0]
    except:
        total_anle = total_precedents = total_phapdien = total_glossary = 0

    conn.close()

    content_size = os.path.getsize(CONTENT_DB) if os.path.exists(CONTENT_DB) else 0

    return {
        "total_documents": total,
        "with_content": with_content,
        "without_content": without_content,
        "progress_pct": round(with_content / total * 100, 2) if total > 0 else 0,
        "by_type": by_type,
        "total_relationships": total_rels,
        "total_modifications": total_mods,
        "fts_indexed": fts_count,
        "total_anle": total_anle,
        "total_precedents": total_precedents,
        "total_phapdien": total_phapdien,
        "total_glossary": total_glossary,
        "content_db_size_mb": round(content_size / 1024 / 1024, 1),
        "main_db_size_mb": round(os.path.getsize(DB_NAME) / 1024 / 1024, 1),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/logs")
def dashboard_logs():
    all_lines = []
    for log_file in ["fill_missing.log", "sync.log"]:
        log_path = os.path.join(_PROJECT_ROOT, log_file)
        if os.path.isfile(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    all_lines.extend(lines)
            except Exception:
                pass
    return {"lines": all_lines[-100:], "total_lines": len(all_lines)}


@router.get("/sample")
def dashboard_sample(limit: int = 20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh, tinh_trang_hieu_luc
        FROM documents WHERE has_content = 1
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    docs = []
    for row in c.fetchall():
        doc = dict(row)
        # Check content length
        try:
            conn_c = get_content_connection()
            cc = conn_c.cursor()
            cc.execute("SELECT LENGTH(content_html) FROM document_content WHERE doc_id = ?", (row["id"],))
            cr = cc.fetchone()
            doc["content_length"] = cr[0] if cr else 0
            conn_c.close()
        except:
            doc["content_length"] = 0
        docs.append(doc)
    conn.close()
    return {"documents": docs}


@router.get("/check")
def dashboard_check(id: int = Query(...)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE id = ?", (id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": f"Document {id} not found"}

    doc = dict(row)

    # Content preview
    try:
        conn_c = get_content_connection()
        cc = conn_c.cursor()
        cc.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (id,))
        cr = cc.fetchone()
        if cr and cr[0]:
            doc["content_preview"] = cr[0][:2000]
            doc["content_length"] = len(cr[0])
        else:
            doc["content_preview"] = None
            doc["content_length"] = 0
        conn_c.close()
    except:
        doc["content_preview"] = None
        doc["content_length"] = 0

    # Relationships
    c.execute("""
        SELECT r.other_doc_id, r.relationship, d.title
        FROM relationships r
        LEFT JOIN documents d ON d.id = r.other_doc_id
        WHERE r.doc_id = ? LIMIT 20
    """, (id,))
    doc["relationships"] = [
        {"other_id": r[0], "type": r[1], "other_title": r[2]}
        for r in c.fetchall()
    ]

    # Modifications
    try:
        c.execute("""
            SELECT am.article_name, am.modified_by_doc_id, am.modified_text, d.title
            FROM article_modifications am
            LEFT JOIN documents d ON d.id = am.modified_by_doc_id
            WHERE am.doc_id = ? LIMIT 20
        """, (id,))
        doc["modifications"] = [
            {"article": r[0], "by_doc_id": r[1], "text": (r[2] or "")[:200], "by_title": r[3]}
            for r in c.fetchall()
        ]
    except:
        doc["modifications"] = []

    conn.close()
    return doc


@router.get("/crawler/progress")
def dashboard_crawler_progress():
    """Đọc progress từ crawler_progress.json — Dashboard poll mỗi 2s."""
    progress_file = os.path.join(_PROJECT_ROOT, "crawler_progress.json")
    pid_file = os.path.join(_PROJECT_ROOT, "crawler.pid")

    # Check if crawler process is alive
    is_running = False
    pid = None
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # Check if alive
            is_running = True
        except (ProcessLookupError, ValueError, PermissionError):
            is_running = False
            try:
                os.remove(pid_file)
            except:
                pass

    if os.path.exists(progress_file):
        try:
            with open(progress_file, encoding="utf-8") as f:
                data = json.load(f)
            data["is_running"] = is_running
            data["pid"] = pid
            return data
        except:
            pass

    return {"status": "idle", "is_running": False, "total": 0, "success": 0, "fail": 0}


@router.post("/crawler/start")
async def dashboard_crawler_start(request: Request):
    """Start crawler as subprocess. Headless trên Linux server, headed trên macOS."""
    pid_file = os.path.join(_PROJECT_ROOT, "crawler.pid")

    # Check if already running
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return {"ok": False, "error": "Crawler đang chạy rồi!", "pid": pid}
        except (ProcessLookupError, ValueError):
            try:
                os.remove(pid_file)
            except:
                pass

    body = await request.json()
    tabs = body.get("tabs", 5)
    limit = body.get("limit", 0)

    script = os.path.join(_PROJECT_ROOT, "fill_missing_content.py")
    cmd = ["python", script]
    if limit and limit > 0:
        cmd.append(str(limit))

    env = os.environ.copy()
    env["CRAWLER_TABS"] = str(tabs)
    # Auto-detect: headless on Linux, headed on macOS
    import platform
    if platform.system() == "Linux":
        env["CRAWLER_HEADLESS"] = "1"

    _crawler_process = subprocess.Popen(cmd, env=env, cwd=_PROJECT_ROOT)
    return {"ok": True, "pid": _crawler_process.pid, "tabs": tabs, "limit": limit,
            "headless": env.get("CRAWLER_HEADLESS", "0") == "1"}


@router.post("/crawler/stop")
def dashboard_crawler_stop():
    """Gửi SIGTERM để crawler dừng an toàn."""
    pid_file = os.path.join(_PROJECT_ROOT, "crawler.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            return {"ok": True, "message": f"Đã gửi tín hiệu dừng (PID {pid}). Crawler sẽ kết thúc an toàn."}
        except ProcessLookupError:
            try:
                os.remove(pid_file)
            except:
                pass
            return {"ok": True, "message": "Crawler đã dừng trước đó."}
        except Exception as e:
            return {"ok": False, "message": str(e)}
    return {"ok": False, "message": "Không có crawler nào đang chạy."}


@router.post("/sync/start")
async def dashboard_sync_start(request: Request):
    body = await request.json()
    pages = body.get("pages", 5)
    script = os.path.join(_PROJECT_ROOT, "sync_new_laws.py")
    if os.path.exists(script):
        env = os.environ.copy()
        env["MAX_PAGES"] = str(pages)
        subprocess.Popen(["python", script], env=env, cwd=_PROJECT_ROOT)
        return {"ok": True, "message": f"Sync đã bắt đầu (quét {pages} trang)"}
    return {"ok": False, "message": "Script không tồn tại"}


@router.post("/tools/rebuild-fts")
def dashboard_rebuild_fts():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        # 1. Documents FTS
        conn.execute("DROP TABLE IF EXISTS documents_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                title, so_ky_hieu, content='documents', content_rowid='id', tokenize='unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO documents_fts(rowid, title, so_ky_hieu)
            SELECT id, title, so_ky_hieu FROM documents
        """)

        # 2. Anle FTS
        conn.execute("DROP TABLE IF EXISTS anle_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE anle_fts USING fts5(
                title, subject, principle_text, content='anle_documents', content_rowid='rowid', tokenize='unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO anle_fts(rowid, title, subject, principle_text)
            SELECT rowid, title, subject, principle_text FROM anle_documents
        """)

        # 3. Phapdien FTS
        conn.execute("DROP TABLE IF EXISTS phapdien_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE phapdien_fts USING fts5(
                article_title, content_text, content='phapdien_articles', content_rowid='rowid', tokenize='unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO phapdien_fts(rowid, article_title, content_text)
            SELECT rowid, article_title, content_text FROM phapdien_articles
        """)

        conn.commit()
        conn.close()
        return {"ok": True, "message": "FTS indexes cho Luật, Án Lệ, Pháp Điển đã được rebuild thành công!"}
    except Exception as e:
        conn.close()
        return {"ok": False, "message": str(e)}


@router.post("/tools/extract-mods")
def dashboard_extract_mods():
    script = os.path.join(_PROJECT_ROOT, "extract_modifications.py")
    if os.path.exists(script):
        subprocess.Popen(["python", script], cwd=_PROJECT_ROOT)
        return {"ok": True, "message": "Extract modifications đã bắt đầu"}
    return {"ok": False, "message": "Script không tồn tại"}


@router.post("/tools/build-crosslinks")
def dashboard_build_crosslinks():
    script = os.path.join(_PROJECT_ROOT, "build_crosslinks.py")
    if os.path.exists(script):
        subprocess.Popen(["python", script], cwd=_PROJECT_ROOT)
        return {"ok": True, "message": "Build crosslinks đã bắt đầu"}
    return {"ok": False, "message": "Script không tồn tại"}
