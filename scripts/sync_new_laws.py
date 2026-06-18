"""
sync_new_laws.py — Đồng bộ VB pháp luật mới từ vbpl.vn (phiên bản 2026)

vbpl.vn đã nâng cấp lên Next.js SPA (4/2026):
  - List: https://vbpl.vn/van-ban/trung-uong
  - Detail: https://vbpl.vn/van-ban/chi-tiet/{slug}
  - Document cards dùng <div> với class DocumentCard_documentCard__*
  - Không có <a href> cho documents, dùng onClick + router.push

Env vars:
  SYNC_PAGES=5          Số trang tối đa (mặc định 5)
  CRAWLER_PROXY=...     Proxy (http://user:pass@ip:port)
  CRAWLER_HEADLESS=1    Headless mode
"""

import os
# Set single-thread CPU execution for PyTorch, FAISS, and OpenBLAS to prevent deadlocks and segfaults
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import re
import sys
import time
import json
import signal
import sqlite3
import asyncio
import platform
import gc
from urllib.parse import quote
from playwright.async_api import async_playwright

# Thêm thư mục gốc vào path để import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import DB_NAME, CONTENT_DB, VECTOR_DB_SOTA, FAISS_INDEX_SOTA, EMBEDDING_MODEL_SOTA, ZVEC_DB_PATH
import zvec
from bs4 import BeautifulSoup

LOG_NAME = "sync.log"
PROGRESS_FILE = "sync_progress.json"
PID_FILE = "sync.pid"

BASE_URL = "https://vbpl.vn"
LIST_URL = f"{BASE_URL}/van-ban/trung-uong"

_shutdown = False


def handle_signal(sig, frame):
    global _shutdown
    _shutdown = True
    log("⛔ Nhận tín hiệu dừng...")


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
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass


def get_total_docs():
    if not os.path.exists(DB_NAME):
        return 0
    conn = sqlite3.connect(DB_NAME)
    total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    return total


def doc_exists_by_title_or_so(title, so_ky_hieu):
    if not os.path.exists(DB_NAME):
        return False
    conn = sqlite3.connect(DB_NAME)
    if so_ky_hieu:
        exists = conn.execute(
            "SELECT 1 FROM documents WHERE so_ky_hieu = ? LIMIT 1", (so_ky_hieu,)
        ).fetchone()
        if exists:
            conn.close()
            return True
    if title:
        exists = conn.execute(
            "SELECT 1 FROM documents WHERE title = ? LIMIT 1", (title,)
        ).fetchone()
        if exists:
            conn.close()
            return True
    conn.close()
    return False


def get_next_doc_id():
    conn = sqlite3.connect(DB_NAME)
    max_id = conn.execute("SELECT MAX(id) FROM documents").fetchone()[0] or 0
    conn.close()
    return max_id + 1


def extract_so_hieu(title):
    """Trích xuất số hiệu từ title."""
    m = re.search(r'(\d+/\d{4}/[A-ZĐa-zđ\-]+)', title)
    if m:
        return m.group(1)
    m = re.search(r'số\s+(\d+/\d{4}/[A-ZĐa-zđ\-]+)', title, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def save_document(title, so_hieu, ngay_bh, loai_vb, co_quan, tinh_trang,
                  ngay_hieu_luc, content_html):
    doc_id = get_next_doc_id()
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        INSERT OR IGNORE INTO documents (
            id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban,
            co_quan_ban_hanh, tinh_trang_hieu_luc, has_content
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, title, so_hieu, ngay_bh, loai_vb, co_quan, tinh_trang,
          1 if content_html else 0))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
            (doc_id, title, so_hieu)
        )
    except:
        pass
    conn.commit()
    conn.close()

    if content_html and os.path.exists(CONTENT_DB):
        conn_c = sqlite3.connect(CONTENT_DB, timeout=30)
        conn_c.execute("PRAGMA journal_mode=WAL")
        conn_c.execute(
            "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
            (doc_id, content_html)
        )
        conn_c.commit()
        conn_c.close()

    return doc_id


async def extract_list_items(page):
    """Trích xuất danh sách VB từ trang list.
    vbpl.vn v2026: DocumentCard divs, không phải <a> tags.
    """
    items = await page.evaluate("""
    () => {
        const items = [];
        const cards = document.querySelectorAll('[class*="documentCard"], [class*="DocumentCard"]');

        for (let i = 0; i < cards.length; i++) {
            const card = cards[i];
            const cardText = card.textContent || '';

            // Title: tìm text dài nhất trong card
            let title = '';
            const els = card.querySelectorAll('div, span, h3, h4, p');
            for (const el of els) {
                const t = el.textContent.trim();
                if (t.length > title.length && t.length > 30) {
                    title = t;
                }
            }
            if (!title || title.length < 15) continue;

            // Date
            let ngay_bh = '';
            const dm = cardText.match(/(\\d{2}\\/\\d{2}\\/\\d{4})/);
            if (dm) ngay_bh = dm[1];

            // Status
            let tinh_trang = '';
            if (cardText.includes('Còn hiệu lực')) tinh_trang = 'Còn hiệu lực';
            else if (cardText.includes('Hết hiệu lực')) tinh_trang = 'Hết hiệu lực';

            items.push({ title, index: i, ngay_bh, tinh_trang });
        }
        return items;
    }
    """)
    return items


async def navigate_to_detail(page, card_index):
    """Click vào document card và lấy URL chi tiết."""
    try:
        result = await page.evaluate("""
        (idx) => {
            const cards = document.querySelectorAll('[class*="documentCard"], [class*="DocumentCard"]');
            if (idx >= cards.length) return null;
            const card = cards[idx];
            // Click the title area (first long text div)
            const els = card.querySelectorAll('div, span');
            for (const el of els) {
                if (el.textContent.trim().length > 30) {
                    el.click();
                    return true;
                }
            }
            card.click();
            return true;
        }
        """, card_index)

        if not result:
            return None

        # Wait for navigation
        await page.wait_for_url("**/chi-tiet/**", timeout=10000)
        await page.wait_for_timeout(2000)

        url = page.url
        if 'chi-tiet' in url:
            return url

        return None
    except Exception as e:
        log(f"   ⚠️ Lỗi navigate card {card_index}: {str(e)[:60]}")
        return None


async def extract_detail_content(page):
    """Trích xuất metadata + nội dung từ trang chi tiết."""
    try:
        # Wait for content to render
        await page.wait_for_timeout(3000)

        meta = await page.evaluate("""
        () => {
            const r = { title:'', so_hieu:'', ngay_bh:'', loai_vb:'', co_quan:'',
                        tinh_trang:'', ngay_hieu_luc:'' };
            const h1 = document.querySelector('h1, [class*="title"]');
            if (h1) r.title = h1.textContent.trim();
            const text = document.body.innerText || '';
            const p = [
                [/Số hiệu[:\\s]+([^\\n]+)/i, 'so_hieu'],
                [/Ngày ban hành[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_bh'],
                [/Loại văn bản[:\\s]+([^\\n]+)/i, 'loai_vb'],
                [/Cơ quan ban hành[:\\s]+([^\\n]+)/i, 'co_quan'],
                [/(Còn hiệu lực|Hết hiệu lực|Chờ hiệu lực)/i, 'tinh_trang'],
                [/Ngày (?:có )?hiệu lực[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_hieu_luc'],
            ];
            for (const [rx, f] of p) { const m = text.match(rx); if (m) r[f] = m[1].trim(); }
            return r;
        }
        """)

        content_html = await page.evaluate("""
        () => {
            const sels = ['[class*="fulltext"]','[class*="full-text"]','[class*="content-detail"]',
                          '[class*="document-content"]','[class*="noi-dung"]','[class*="tab-content"]',
                          'article','main'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.innerHTML.length > 200) return el.innerHTML;
            }
            // Fallback: largest div with "Điều"
            let best = '', bestLen = 0;
            for (const d of document.querySelectorAll('div')) {
                if (d.innerHTML.length > 500 && d.innerHTML.includes('Điều') && d.innerHTML.length > bestLen) {
                    bestLen = d.innerHTML.length; best = d.innerHTML;
                }
            }
            return best;
        }
        """)

        return meta, content_html
    except Exception as e:
        log(f"   ⚠️ Lỗi extract detail: {str(e)[:60]}")
        return None, None


def remove_watermarks(html_content: str) -> str:
    if not html_content:
        return ""
    cleaned = html_content
    promotional_keywords = [
        r"Bản quyền\s+©\s+\d{4}-\d{4}\s+bởi\s+LuatVietnam.*",
        r"Chứng nhận bản quyền tác giả số.*",
        r"www\.LuatVietnam\.vn",
        r"LuatVietnam\.vn",
        r"Tổng đài trực tuyến\s+\d+",
        r"Tổng đài tư vấn\s+\d+",
        r"Hỗ trợ giải đáp pháp luật:\s*\d+",
        r"Điện thoại:\s*\d+\s*-\s*Email:\s*[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        r"Đây là tiện ích dành cho thành viên đăng ký phần mềm.*",
        r"Vui lòng Đăng nhập tài khoản để xem chi tiết.*",
        r"Tiện ích dành cho tài khoản.*",
        r"Vui lòng liên hệ.* để được hỗ trợ.*",
    ]
    for pat in promotional_keywords:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    return cleaned


async def crawl_luatvietnam_detail(page, detail_url):
    try:
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        
        meta = await page.evaluate("""
        () => {
            const r = { title:'', so_hieu:'', ngay_bh:'', loai_vb:'', co_quan:'', tinh_trang:'', ngay_hieu_luc:'', linh_vuc:'' };
            const h1 = document.querySelector('h1');
            if (h1) r.title = h1.textContent.trim();
            const table = document.querySelector('table');
            if (table) {
                const text = table.innerText || '';
                const p = [
                    [/Số hiệu[:\\s]+([^\\n]+)/i, 'so_hieu'],
                    [/Ngày ban hành[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_bh'],
                    [/Loại văn bản[:\\s]+([^\\n]+)/i, 'loai_vb'],
                    [/Cơ quan ban hành[:\\s]+([^\\n]+)/i, 'co_quan'],
                    [/Tình trạng hiệu lực[:\\s]+([^\\n]+)/i, 'tinh_trang'],
                    [/Ngày hết hiệu lực[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_hieu_luc'],
                    [/Lĩnh vực[:\\s]+([^\\n]+)/i, 'linh_vuc'],
                ];
                for (const [rx, f] of p) { const m = text.match(rx); if (m) r[f] = m[1].trim(); }
            }
            return r;
        }
        """)
        
        content_html = await page.evaluate("""
        () => {
            const divs = document.querySelectorAll('div');
            let best = '', bestLen = 0;
            for (const d of divs) {
                const classes = d.className || '';
                if (classes.includes('tab-noi-dung') || classes.includes('tab-content')) {
                    const textLen = (d.textContent || '').trim().length;
                    if (textLen > bestLen && textLen > 500) {
                        bestLen = textLen;
                        best = d.innerHTML;
                    }
                }
            }
            return best;
        }
        """)
        return meta, content_html
    except Exception as e:
        log(f"   ⚠️ Lỗi crawl detail LuatVietnam: {str(e)[:60]}")
        return None, None


async def crawl_phapluat_detail(page, context, card_index):
    try:
        async with context.expect_page(timeout=10000) as new_page_info:
            await page.evaluate(f"""
            (idx) => {{
                const els = document.querySelectorAll('div[class*="cursor-pointer"]');
                let card_idx = 0;
                for (const el of els) {{
                    const text = el.textContent.trim();
                    if (text.includes('Quyết định') || text.includes('Nghị định') || text.includes('Thông tư')) {{
                        if (card_idx === idx) {{
                            el.click();
                            return true;
                        }}
                        card_idx++;
                    }}
                }}
                return false;
            }}
            """, card_index)
            
        new_page = await new_page_info.value
        await new_page.wait_for_timeout(8000)
        
        meta = await new_page.evaluate("""
        () => {
            const r = { title:'', so_hieu:'', ngay_bh:'', loai_vb:'', co_quan:'', tinh_trang:'', ngay_hieu_luc:'' };
            const h1 = document.querySelector('h1, h2, [class*="title"]');
            if (h1) r.title = h1.textContent.trim();
            const text = document.body.innerText || '';
            const p = [
                [/Số hiệu[:\\s]+([^\\n]+)/i, 'so_hieu'],
                [/Ngày ban hành[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_bh'],
                [/Loại văn bản[:\\s]+([^\\n]+)/i, 'loai_vb'],
                [/Cơ quan ban hành[:\\s]+([^\\n]+)/i, 'co_quan'],
                [/Tình trạng hiệu lực[:\\s]+([^\\n]+)/i, 'tinh_trang'],
                [/Ngày hết hiệu lực[:\\s]+(\\d{2}\\/\\d{2}\\/\\d{4})/i, 'ngay_hieu_luc'],
            ];
            for (const [rx, f] of p) { const m = text.match(rx); if (m) r[f] = m[1].trim(); }
            return r;
        }
        """)
        
        content_html = await new_page.evaluate("""
        () => {
            const el = document.querySelector('div.document-content');
            return el ? el.innerHTML : '';
        }
        """)
        await new_page.close()
        return meta, content_html
    except Exception as e:
        log(f"   ⚠️ Lỗi crawl detail PhapLuat: {str(e)[:60]}")
        return None, None


async def sync_luatvietnam_source(page, stats):
    url = "https://luatvietnam.vn/van-ban-moi.html"
    log(f"🔍 Mở trang danh sách LuatVietnam: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
    except Exception as e:
        log(f"❌ Không thể mở trang LuatVietnam: {e}")
        return
        
    for page_idx in range(1, 3):
        if _shutdown:
            break
        log(f"📄 LuatVietnam — Trang {page_idx}...")
        
        posts = await page.evaluate("""
        () => {
            const items = [];
            const divs = document.querySelectorAll('div.post-doc');
            divs.forEach((d, idx) => {
                const title_a = d.querySelector('h2.doc-title a') || d.querySelector('a');
                if (title_a) {
                    items.push({
                        title: title_a.textContent.trim(),
                        href: title_a.getAttribute('href'),
                        index: idx
                    });
                }
            });
            return items;
        }
        """)
        
        if not posts:
            log(f"⚠️ Không tìm thấy văn bản nào ở trang {page_idx}")
            break
            
        existing_count = 0
        for item in posts:
            if _shutdown:
                break
            title = item["title"]
            href = item["href"]
            if not href or href.startswith("javascript"):
                continue
                
            so_hieu = extract_so_hieu(title)
            if doc_exists_by_title_or_so(title, so_hieu):
                existing_count += 1
                stats["skipped"] += 1
                continue
                
            detail_url = f"https://luatvietnam.vn{href}"
            log(f"   ✨ VB LuatVietnam mới: {so_hieu or 'N/A'} — {title[:70]}...")
            
            meta, content_html = await crawl_luatvietnam_detail(page, detail_url)
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            
            if meta is None or not content_html:
                stats["errors"] += 1
                continue
                
            final_title = meta.get("title") or title
            final_so_hieu = meta.get("so_hieu") or so_hieu
            ngay_bh = meta.get("ngay_bh") or ""
            loai_vb = meta.get("loai_vb") or "Quyết định"
            co_quan = meta.get("co_quan") or ""
            tinh_trang = meta.get("tinh_trang") or "Còn hiệu lực"
            ngay_hieu_luc = meta.get("ngay_hieu_luc") or ""
            
            doc_id = save_document(
                final_title, final_so_hieu, ngay_bh, loai_vb,
                co_quan, tinh_trang, ngay_hieu_luc, content_html
            )
            
            index_document_incrementally(doc_id, final_title, final_so_hieu, loai_vb, content_html)
            stats["new_docs"] += 1
            log(f"   ✅ ID {doc_id} ({final_so_hieu}) đồng bộ thành công")
            
        if existing_count == len(posts) and len(posts) > 0:
            log("📌 Tất cả văn bản LuatVietnam trên trang này đã tồn tại. Dừng.")
            break
            
        if page_idx < 2:
            next_url = f"https://luatvietnam.vn/van-ban-moi.html?PageSize=20&PageIndex={page_idx + 1}"
            await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)


async def sync_phapluat_source(page, context, stats):
    url = "https://phapluat.gov.vn/he-thong-van-ban-phap-luat"
    log(f"🔍 Mở trang danh sách PhapLuat: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
    except Exception as e:
        log(f"❌ Không thể mở trang PhapLuat: {e}")
        return
        
    for page_idx in range(1, 3):
        if _shutdown:
            break
        log(f"📄 PhapLuat — Trang {page_idx}...")
        
        cards = await page.evaluate("""
        () => {
            const items = [];
            const els = document.querySelectorAll('div[class*="cursor-pointer"]');
            let card_idx = 0;
            for (let el of els) {
                const text = el.textContent.trim();
                if (text.includes('Quyết định') || text.includes('Nghị định') || text.includes('Thông tư')) {
                    let card_parent = el.closest('.flex-1');
                    let ngay_bh = '';
                    let ngay_hieu_luc = '';
                    let tinh_trang = 'Còn hiệu lực';
                    
                    if (card_parent) {
                        const grid = card_parent.querySelector('div[class*="grid-cols-[5rem_1fr]"]');
                        if (grid) {
                            const spans = grid.querySelectorAll('span');
                            for (let j = 0; j < spans.length - 1; j += 2) {
                                const lbl = spans[j].textContent.trim();
                                const val = spans[j+1].textContent.trim();
                                if (lbl.includes('Ban hành')) ngay_bh = val;
                                else if (lbl.includes('Áp dụng')) ngay_hieu_luc = val;
                                else if (lbl.includes('Hiệu lực')) tinh_trang = val;
                            }
                        }
                    }
                    
                    items.push({
                        title: text,
                        index: card_idx,
                        ngay_bh: ngay_bh,
                        ngay_hieu_luc: ngay_hieu_luc,
                        tinh_trang: tinh_trang
                    });
                    card_idx++;
                }
            }
            return items;
        }
        """)
        
        if not cards:
            log(f"⚠️ Không tìm thấy văn bản nào ở trang {page_idx}")
            break
            
        existing_count = 0
        for item in cards:
            if _shutdown:
                break
            title = item["title"]
            so_hieu = extract_so_hieu(title)
            
            if doc_exists_by_title_or_so(title, so_hieu):
                existing_count += 1
                stats["skipped"] += 1
                continue
                
            log(f"   ✨ VB PhapLuat mới: {so_hieu or 'N/A'} — {title[:70]}...")
            
            meta, content_html = await crawl_phapluat_detail(page, context, item["index"])
            if meta is None or not content_html:
                stats["errors"] += 1
                continue
                
            final_title = meta.get("title") or title
            final_so_hieu = meta.get("so_hieu") or so_hieu
            ngay_bh = meta.get("ngay_bh") or item["ngay_bh"]
            loai_vb = meta.get("loai_vb") or "Quyết định"
            co_quan = meta.get("co_quan") or ""
            tinh_trang = meta.get("tinh_trang") or item["tinh_trang"]
            ngay_hieu_luc = meta.get("ngay_hieu_luc") or item["ngay_hieu_luc"]
            
            doc_id = save_document(
                final_title, final_so_hieu, ngay_bh, loai_vb,
                co_quan, tinh_trang, ngay_hieu_luc, content_html
            )
async def run_sync():
    global _shutdown

    MAX_PAGES = int(os.environ.get("SYNC_PAGES", "5"))
    PROXY = os.environ.get("CRAWLER_PROXY", "").strip()
    HEADLESS = os.environ.get("CRAWLER_HEADLESS", "")
    if not HEADLESS:
        HEADLESS = platform.system() == "Linux"
    else:
        HEADLESS = HEADLESS == "1"

    total_before = get_total_docs()
    log("=" * 60)
    log("🚀 ĐỒNG BỘ VB MỚI TỪ CÁC NGUỒN (VBPL, LUATVIETNAM, PHAPLUAT.GOV.VN)")
    log(f"📊 Tổng VB hiện tại: {total_before:,}")
    log(f"⚙️  Max pages: {MAX_PAGES}, Proxy: {PROXY or 'none'}, Headless: {HEADLESS}")
    log("=" * 60)

    stats = {
        "status": "running",
        "type": "sync",
        "total_before": total_before,
        "new_docs": 0,
        "skipped": 0,
        "errors": 0,
        "pages_scanned": 0,
        "max_pages": MAX_PAGES,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "recent": [],
    }
    write_progress(stats)

    async with async_playwright() as p:
        launch_args = [
            "--ignore-certificate-errors",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        launch_opts = {"headless": HEADLESS, "args": launch_args}
        if PROXY:
            launch_opts["proxy"] = {"server": PROXY}
            log(f"🌐 Proxy: {PROXY}")

        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        # Nguồn 1: vbpl.vn
        log("\n--- BẮT ĐẦU ĐỒNG BỘ NGUỒN 1: VBPL.VN ---")
        try:
            log(f"🔍 Mở trang danh sách: {LIST_URL}")
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector('[class*="documentCard"], [class*="DocumentCard"]', timeout=15000)
                log("✅ Trang list đã load, tìm thấy DocumentCards")
            except:
                await page.wait_for_timeout(8000)
                log("⚠️ Chờ thêm 8s cho JS render...")
                
            for page_idx in range(1, MAX_PAGES + 1):
                if _shutdown:
                    break
                log(f"📄 Xử lý trang {page_idx}/{MAX_PAGES}...")
                stats["pages_scanned"] = page_idx
                
                items = []
                for _ in range(8):
                    items = await extract_list_items(page)
                    if items:
                        break
                    await page.wait_for_timeout(2000)
                    
                if not items:
                    log(f"⚠️ Không tìm thấy VB nào trên trang {page_idx}. Dừng.")
                    break
                    
                log(f"   📊 Tìm thấy {len(items)} VB")
                existing_count = 0
                
                for item in items:
                    if _shutdown:
                        break
                    title = item["title"]
                    so_hieu = extract_so_hieu(title)
                    
                    if doc_exists_by_title_or_so(title, so_hieu):
                        existing_count += 1
                        stats["skipped"] += 1
                        continue
                        
                    log(f"   ✨ VB mới: {so_hieu or 'N/A'} — {title[:70]}...")
                    detail_url = await navigate_to_detail(page, item["index"])
                    
                    if not detail_url:
                        stats["errors"] += 1
                        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=20000)
                        await page.wait_for_timeout(5000)
                        continue
                        
                    meta, content_html = await extract_detail_content(page)
                    if meta is None:
                        stats["errors"] += 1
                        await page.go_back()
                        await page.wait_for_timeout(3000)
                        continue
                        
                    final_title = meta.get("title") or title
                    final_so_hieu = meta.get("so_hieu") or so_hieu
                    ngay_bh = meta.get("ngay_bh") or item.get("ngay_bh", "")
                    loai_vb = meta.get("loai_vb") or "Văn bản pháp luật"
                    co_quan = meta.get("co_quan") or ""
                    tinh_trang = meta.get("tinh_trang") or item.get("tinh_trang", "Còn hiệu lực")
                    ngay_hieu_luc = meta.get("ngay_hieu_luc") or ""
                    
                    doc_id = save_document(
                        final_title, final_so_hieu, ngay_bh, loai_vb,
                        co_quan, tinh_trang, ngay_hieu_luc, content_html
                    )
                    
                    index_document_incrementally(doc_id, final_title, final_so_hieu, loai_vb, content_html)
                    stats["new_docs"] += 1
                    
                    stats["recent"] = ([{
                        "id": doc_id,
                        "title": final_title[:60],
                        "so_hieu": final_so_hieu,
                        "time": time.strftime("%H:%M:%S"),
                        "has_content": bool(content_html),
                    }] + stats["recent"])[:20]
                    write_progress(stats)
                    
                    await page.go_back()
                    await page.wait_for_timeout(3000)
                    
                if existing_count == len(items) and len(items) > 0:
                    log(f"📌 Tất cả {len(items)} VB trên trang {page_idx} đã có trong DB. Dừng.")
                    break
                    
                if page_idx < MAX_PAGES:
                    has_next = await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button, a, li');
                        for (const b of btns) {
                            const t = b.textContent.trim();
                            const label = b.getAttribute('aria-label') || '';
                            if ((t === '>' || t === '›' || t === 'Sau' || t === 'Next' ||
                                 label.toLowerCase().includes('next')) &&
                                !b.disabled && b.offsetParent !== null) {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    """)
                    if not has_next:
                        break
                    await page.wait_for_timeout(5000)
        except Exception as e:
            log(f"❌ Lỗi đồng bộ nguồn VBPL: {e}")

        # Nguồn 2: luatvietnam.vn
        if not _shutdown:
            log("\n--- BẮT ĐẦU ĐỒNG BỘ NGUỒN 2: LUATVIETNAM.VN ---")
            try:
                await sync_luatvietnam_source(page, stats)
            except Exception as e:
                log(f"❌ Lỗi đồng bộ nguồn LuatVietnam: {e}")

        # Nguồn 3: phapluat.gov.vn
        if not _shutdown:
            log("\n--- BẮT ĐẦU ĐỒNG BỘ NGUỒN 3: PHAPLUAT.GOV.VN ---")
            try:
                await sync_phapluat_source(page, context, stats)
            except Exception as e:
                log(f"❌ Lỗi đồng bộ nguồn PhapLuat: {e}")

        await browser.close()

    total_after = get_total_docs()
    stats["status"] = "completed" if not _shutdown else "stopped"
    stats["total_after"] = total_after
    stats["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_progress(stats)

    log("=" * 60)
    log("🎉 HOÀN THÀNH ĐỒNG BỘ!")
    log(f"   📄 VB mới thêm: {stats['new_docs']}")
    log(f"   ⏭️  Đã có sẵn: {stats['skipped']}")
    log(f"   ❌ Lỗi: {stats['errors']}")
    log(f"   📑 Trang quét: {stats['pages_scanned']}")
    log(f"   📊 Tổng DB: {total_before:,} → {total_after:,}")
    log("=" * 60)


def index_document_incrementally(doc_id, title, so_ky_hieu, loai_van_ban, content_html):
    """
    Tự động chia nhỏ, sinh vector nhúng bằng BGE-M3, lưu vào cache SQLite và xây dựng đồ thị tri thức,
    sau đó cập nhật gia tăng các chỉ mục FAISS (Flat, SQ8, IVF-SQ8) cho tài liệu mới đồng bộ.
    """
    if not content_html:
        return
        
    try:
        from bs4 import BeautifulSoup
        from scratch.build_chunks_v2 import parse_html_to_chunks
        from app.utils.light_graph_manager import LightGraphManager
        import sqlite3
        import numpy as np
        import faiss
        
        log(f"   ⚡ Bắt đầu đồng bộ chỉ mục gia tăng cho văn bản ID: {doc_id}...")
        
        # Clean watermarks/copyright lines before chunking
        cleaned_html = remove_watermarks(content_html)
        
        # 1. Cắt văn bản thành các chunks
        chunks = parse_html_to_chunks(cleaned_html)
        if not chunks:
            return
            
        # 2. Xây dựng đồ thị tri thức (Knowledge Graph)
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text()
        LightGraphManager.index_document_graph(doc_id, title, so_ky_hieu, text)
        
        # 3. Kết nối CSDL chính để lưu các chunks
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        
        # Xóa các chunks cũ của văn bản này để tránh trùng lặp trong SQLite và FTS index
        cursor.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))
        
        chunks_data = []
        for c in chunks:
            chunk_header = c["chunk_header"] or ""
            chunk_text = c["chunk_text"] or ""
            chunk_with_meta = f"[{so_ky_hieu}] [{loai_van_ban}] [{title}] [{chunk_header}]\n{chunk_text}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO document_chunks 
                (doc_id, chunk_index, chunk_type, chunk_header, chunk_text, chunk_with_meta, token_estimate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, c["chunk_index"], c["chunk_type"], chunk_header, chunk_text, chunk_with_meta, c["token_estimate"]))
            
            chunk_uid = cursor.lastrowid
            chunks_data.append((chunk_uid, chunk_with_meta))
            
        conn.commit()
        conn.close()
        
        # 4. Sinh vector embeddings bằng model BGE-M3 (1024-dim)
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBEDDING_MODEL_SOTA, device="cpu")
        model.max_seq_length = 512
        
        texts = [cd[1] for cd in chunks_data]
        embeddings = model.encode(texts, batch_size=len(texts), convert_to_numpy=True)
        embeddings = embeddings.astype(np.float32)
        
        # 5. Lưu vectors vào cache VECTOR_DB_SOTA
        v_conn = sqlite3.connect(VECTOR_DB_SOTA, timeout=30)
        v_cursor = v_conn.cursor()
        for (chunk_uid, _), emb in zip(chunks_data, embeddings):
            v_cursor.execute(
                "INSERT OR REPLACE INTO chunk_vectors (chunk_id, vector) VALUES (?, ?)",
                (chunk_uid, emb.tobytes())
            )
        v_conn.commit()
        v_conn.close()
        
        # 6. Cập nhật các FAISS Index tồn tại trên ổ đĩa
        flat_file = FAISS_INDEX_SOTA
        if flat_file.endswith("_sq8.index"):
            flat_file = flat_file.replace("_sq8.index", ".index")
        elif flat_file.endswith("_ivf_sq8.index"):
            flat_file = flat_file.replace("_ivf_sq8.index", ".index")
            
        sq8_file = flat_file.replace(".index", "_sq8.index")
        ivf_sq8_file = flat_file.replace(".index", "_ivf_sq8.index")
        
        # Chuẩn hóa L2 trước khi đưa vào FAISS
        xb = embeddings.copy()
        faiss.normalize_L2(xb)
        ids = np.array([cd[0] for cd in chunks_data], dtype=np.int64)
        
        for idx_file in [flat_file, sq8_file, ivf_sq8_file]:
            if os.path.exists(idx_file):
                try:
                    index = faiss.read_index(idx_file)
                    index.add_with_ids(xb, ids)
                    faiss.write_index(index, idx_file)
                    log(f"   ⚡ Đã cập nhật gia tăng {len(chunks_data)} vectors vào FAISS index: {idx_file}")
                    del index
                    gc.collect()
                except Exception as ex:
                    log(f"   ⚠️ Lỗi cập nhật gia tăng file index {idx_file}: {ex}")
                    
        # 7. Cập nhật Zvec Collection
        try:
            schema = zvec.CollectionSchema(
                name="zvec_laws",
                vectors=[
                    zvec.VectorSchema("dense_vector", zvec.DataType.VECTOR_FP32, 1024)
                ],
                fields=[
                    zvec.FieldSchema("doc_id", zvec.DataType.INT64),
                    zvec.FieldSchema("so_ky_hieu", zvec.DataType.STRING),
                    zvec.FieldSchema("loai_van_ban", zvec.DataType.STRING),
                    zvec.FieldSchema("tinh_trang_hieu_luc", zvec.DataType.STRING),
                    zvec.FieldSchema("chunk_text", zvec.DataType.STRING)
                ]
            )
            try:
                collection = zvec.open(path=ZVEC_DB_PATH)
            except Exception:
                collection = zvec.create_and_open(path=ZVEC_DB_PATH, schema=schema)
                
            zvec_docs = []
            for (chunk_uid, chunk_with_meta), emb in zip(chunks_data, embeddings):
                zvec_docs.append(zvec.Doc(
                    id=str(chunk_uid),
                    vectors={"dense_vector": emb.tolist()},
                    fields={
                        "doc_id": doc_id,
                        "so_ky_hieu": so_ky_hieu or "",
                        "loai_van_ban": loai_van_ban or "",
                        "tinh_trang_hieu_luc": "Còn hiệu lực",
                        "chunk_text": chunk_with_meta
                    }
                ))
            if zvec_docs:
                batch_size = 1000
                for idx_batch in range(0, len(zvec_docs), batch_size):
                    batch = zvec_docs[idx_batch:idx_batch + batch_size]
                    collection.insert(batch)
                collection.flush()
                log(f"   ⚡ Đã cập nhật gia tăng {len(zvec_docs)} vectors vào Zvec collection tại {ZVEC_DB_PATH}")
        except Exception as ez:
            log(f"   ⚠️ Lỗi cập nhật gia tăng Zvec: {ez}")
            
    except Exception as e:
        log(f"   ⚠️ Lỗi đồng bộ index gia tăng cho ID {doc_id}: {e}")

def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        asyncio.run(run_sync())
    finally:
        try:
            os.remove(PID_FILE)
        except:
            pass


if __name__ == "__main__":
    main()
