"""
fill_missing_content.py — Dùng Playwright (trình duyệt thật) để tải nội dung 
cho các văn bản còn thiếu content, lưu vào DB, extract modifications.

v3 — Server-ready:
  - Ghi progress real-time vào crawler_progress.json → Dashboard đọc
  - Thread-safe DB writes (asyncio.Lock) → không corrupt
  - Block images/CSS → nhanh 3x
  - Auto-retry, rate-limit detection
  - Headless mode cho Linux server (CRAWLER_HEADLESS=1)
  - PID file để server quản lý start/stop

Sử dụng:
    python fill_missing_content.py              # Tải toàn bộ (5 tabs, headed)
    CRAWLER_TABS=8 python fill_missing_content.py 
    CRAWLER_HEADLESS=1 CRAWLER_TABS=5 python fill_missing_content.py  # Linux server
"""
import os
import sys
import re
import time
import sqlite3
import asyncio
import json
import signal
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"
LOG_NAME = "fill_missing.log"
PROGRESS_FILE = "crawler_progress.json"
PID_FILE = "crawler.pid"
BASE_URL = "https://vbpl.vn/van-ban/chi-tiet"

db_lock = asyncio.Lock()
_shutdown = False


def handle_signal(sig, frame):
    global _shutdown
    _shutdown = True
    log("⛔ Nhận tín hiệu dừng, đang kết thúc an toàn...")


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg, flush=True)
    try:
        with open(LOG_NAME, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except:
        pass


def write_progress(data):
    """Ghi progress ra JSON file cho Dashboard đọc."""
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data["updated_ts"] = time.time()
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass


def get_missing_ids(limit=None, offset=0):
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT id FROM documents WHERE has_content = 0 ORDER BY id"
    if limit:
        query += f" LIMIT {limit} OFFSET {offset}"
    ids = [r[0] for r in conn.execute(query).fetchall()]
    conn.close()
    return ids


async def save_content_safe(item_id, content_html, conn_main, conn_content):
    async with db_lock:
        conn_content.execute(
            "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
            (item_id, content_html),
        )
        conn_main.execute("UPDATE documents SET has_content = 1 WHERE id = ?", (item_id,))
        row = conn_main.execute("SELECT title, so_ky_hieu FROM documents WHERE id = ?", (item_id,)).fetchone()
        if row:
            try:
                conn_main.execute(
                    "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
                    (item_id, row[0], row[1]),
                )
            except:
                pass
        mods = extract_modifications(item_id, content_html, conn_main)
        conn_main.commit()
        conn_content.commit()
        return mods


def extract_modifications(item_id, content_html, conn_main):
    rels = conn_main.execute("""
        SELECT other_doc_id, relationship FROM relationships
        WHERE doc_id = ? AND relationship IN ('Văn bản sửa đổi', 'Văn bản bổ sung')
    """, (item_id,)).fetchall()
    if not rels:
        return 0
    soup = BeautifulSoup(content_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    matches = list(re.finditer(r"Sửa đổi.*?Điều\s+(\d+[A-Z]?)", text, re.IGNORECASE))
    inserted = 0
    for other_doc_id, rel in rels:
        for match in matches:
            article = f"Điều {match.group(1)}"
            snippet = text[max(0, match.start()-30):min(len(text), match.end()+200)]
            exists = conn_main.execute(
                "SELECT 1 FROM article_modifications WHERE doc_id=? AND article_name=? AND modified_by_doc_id=?",
                (other_doc_id, article, item_id)
            ).fetchone()
            if not exists:
                try:
                    conn_main.execute(
                        "INSERT INTO article_modifications (doc_id, article_name, modified_by_doc_id, modified_text) VALUES (?, ?, ?, ?)",
                        (other_doc_id, article, item_id, snippet)
                    )
                    inserted += 1
                except:
                    pass
    return inserted


async def crawl_documents(missing_ids):
    global _shutdown
    total = len(missing_ids)
    log(f"🚀 Bắt đầu tải {total} văn bản bằng Playwright...")

    conn_main = sqlite3.connect(DB_NAME, timeout=60)
    conn_main.execute("PRAGMA journal_mode=WAL")
    conn_main.execute("PRAGMA synchronous=NORMAL")
    conn_main.execute("PRAGMA busy_timeout=30000")
    conn_content = sqlite3.connect(CONTENT_DB, timeout=60)
    conn_content.execute("PRAGMA journal_mode=WAL")
    conn_content.execute("PRAGMA synchronous=NORMAL")
    conn_content.execute("PRAGMA busy_timeout=30000")

    NUM_TABS = int(os.environ.get("CRAWLER_TABS", "5"))
    HEADLESS = os.environ.get("CRAWLER_HEADLESS", "0") == "1"
    MAX_RETRIES = 3

    stats = {
        "status": "running",
        "total": total,
        "success": 0,
        "fail": 0,
        "skip": 0,
        "mods": 0,
        "retries": 0,
        "tabs": NUM_TABS,
        "headless": HEADLESS,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_ts": time.time(),
        "current_ids": [],
        "speed": 0,
        "eta_seconds": 0,
        "eta_display": "Tính toán...",
        "error_rate": 0,
        "last_error": "",
        "recent_docs": [],
    }
    write_progress(stats)

    log(f"⚡ Cấu hình: {NUM_TABS} tabs, headless={HEADLESS}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        log(f"⚡ Mở {NUM_TABS} tab trình duyệt song song...")
        pages = []
        for _ in range(NUM_TABS):
            pg = await context.new_page()
            await pg.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,css}",
                          lambda route: route.abort())
            pages.append(pg)

        sem = asyncio.Semaphore(NUM_TABS)

        async def process_one(item_id, tab_idx):
            if _shutdown:
                return
            page = pages[tab_idx % len(pages)]
            
            for attempt in range(MAX_RETRIES):
                if _shutdown:
                    return
                try:
                    resp = await page.goto(f"{BASE_URL}/{item_id}", 
                                          wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(1500)

                    body_text = await page.inner_text("body")

                    if "ERR_CONNECTION" in body_text or len(body_text) < 50:
                        if attempt < MAX_RETRIES - 1:
                            stats["retries"] += 1
                            await page.wait_for_timeout(5000 * (attempt + 1))
                            continue
                        stats["fail"] += 1
                        stats["last_error"] = f"Connection error ID {item_id}"
                        return

                    if "Văn bản không tồn tại" in body_text or "404" in body_text:
                        async with db_lock:
                            conn_main.execute("UPDATE documents SET has_content = -1 WHERE id = ?", (item_id,))
                            conn_main.commit()
                        stats["skip"] += 1
                        return

                    content_html = None
                    for sel in ["[class*='fulltext']", "[class*='FullText']",
                                "[class*='content-detail']", "[class*='ContentDetail']",
                                "[class*='noi-dung']", "article", "main"]:
                        el = page.locator(sel).first
                        if await el.count() > 0:
                            html = await el.inner_html()
                            if len(html) > 100:
                                content_html = html
                                break

                    if not content_html:
                        content_html = await page.inner_html("body")

                    if content_html and len(content_html) > 50:
                        mods = await save_content_safe(item_id, content_html, conn_main, conn_content)
                        stats["success"] += 1
                        stats["mods"] += mods
                        # Track recent docs
                        stats["recent_docs"] = ([{"id": item_id, "time": time.strftime("%H:%M:%S"), 
                                                  "size": len(content_html)}] + stats["recent_docs"])[:20]
                        return
                    else:
                        stats["fail"] += 1
                        return

                except Exception as e:
                    err = str(e)[:100]
                    if ("Timeout" in err or "net::ERR" in err) and attempt < MAX_RETRIES - 1:
                        stats["retries"] += 1
                        await page.wait_for_timeout(3000 * (attempt + 1))
                        continue
                    stats["fail"] += 1
                    stats["last_error"] = f"[Tab{tab_idx}] ID {item_id}: {err}"
                    if stats["fail"] % 10 == 0:
                        log(f"   ❌ [Tab{tab_idx}] ID {item_id}: {err}")
                    return

        async def process_with_sem(item_id, tab_idx):
            async with sem:
                stats["current_ids"] = list(set(stats.get("current_ids", []) + [item_id]))[-NUM_TABS:]
                await process_one(item_id, tab_idx)
                await asyncio.sleep(0.3)

        # Process in chunks
        chunk_size = NUM_TABS * 10
        for chunk_start in range(0, total, chunk_size):
            if _shutdown:
                break

            chunk = missing_ids[chunk_start:chunk_start + chunk_size]
            tasks = [process_with_sem(iid, i) for i, iid in enumerate(chunk)]
            await asyncio.gather(*tasks)

            # Update progress
            done = stats["success"] + stats["fail"] + stats["skip"]
            elapsed = time.time() - stats["started_ts"]
            speed = stats["success"] / elapsed if elapsed > 0 else 0
            remaining = total - done
            eta = remaining / speed if speed > 0 else 0

            stats["speed"] = round(speed, 2)
            stats["eta_seconds"] = round(eta)
            stats["elapsed_seconds"] = round(elapsed)
            stats["done"] = done
            stats["remaining"] = remaining
            stats["progress_pct"] = round(done / total * 100, 1) if total > 0 else 0
            stats["error_rate"] = round(stats["fail"] / done * 100, 1) if done > 0 else 0

            # Format ETA display
            if eta > 3600:
                stats["eta_display"] = f"{eta/3600:.1f}h"
            elif eta > 60:
                stats["eta_display"] = f"{eta/60:.0f}m"
            else:
                stats["eta_display"] = f"{eta:.0f}s"

            # Format elapsed
            if elapsed > 3600:
                stats["elapsed_display"] = f"{elapsed/3600:.1f}h"
            elif elapsed > 60:
                stats["elapsed_display"] = f"{elapsed/60:.0f}m"
            else:
                stats["elapsed_display"] = f"{elapsed:.0f}s"

            write_progress(stats)

            # Log every 50 successes
            if stats["success"] > 0 and stats["success"] % 50 < chunk_size:
                log(f"   ⏳ [{done}/{total}] ✅{stats['success']} ❌{stats['fail']} ⏭️{stats['skip']} "
                    f"🔗{stats['mods']} Speed: {speed:.1f}/s | ETA: {stats['eta_display']}")

            # Stop if error rate too high
            if done > 30 and stats["error_rate"] > 80:
                log("⚠️ Tỷ lệ lỗi >80%, dừng lại. Có thể bị rate-limit.")
                stats["status"] = "error_rate_high"
                write_progress(stats)
                break

        await browser.close()

    conn_main.close()
    conn_content.close()

    elapsed = time.time() - stats["started_ts"]
    stats["status"] = "completed" if not _shutdown else "stopped"
    stats["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    stats["elapsed_seconds"] = round(elapsed)
    stats["current_ids"] = []
    write_progress(stats)

    log("=" * 60)
    log("🎉 HOÀN THÀNH!")
    log(f"   ✅ Thành công: {stats['success']}")
    log(f"   ❌ Thất bại: {stats['fail']}")
    log(f"   ⏭️ Không tồn tại: {stats['skip']}")
    log(f"   🔗 Modifications: {stats['mods']}")
    log(f"   🔄 Retries: {stats['retries']}")
    log(f"   ⏱️ Thời gian: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    log("=" * 60)


def main():
    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    limit = None
    offset = 0
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
    if len(sys.argv) > 2:
        offset = int(sys.argv[2])

    missing_ids = get_missing_ids(limit=limit, offset=offset)
    log(f"📊 Tìm thấy {len(missing_ids)} văn bản cần tải content")

    if not missing_ids:
        log("✅ Tất cả văn bản đã có content!")
        write_progress({"status": "idle", "total": 0, "success": 0, "fail": 0})
        return

    try:
        asyncio.run(crawl_documents(missing_ids))
    finally:
        # Cleanup PID file
        try:
            os.remove(PID_FILE)
        except:
            pass


if __name__ == "__main__":
    main()
