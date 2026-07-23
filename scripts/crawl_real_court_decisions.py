#!/usr/bin/env python3
"""
scripts/crawl_real_court_decisions.py
======================================
Script Cào DỮ LIỆU THẬT từ Cổng Công bố Bản án TANDTC
URL: https://congbobanan.toaan.gov.vn

Nguồn dữ liệu:
- Bản án hình sự, dân sự, hành chính, kinh doanh thương mại
- Dữ liệu công khai theo quy định pháp luật

CÁCH HOẠT ĐỘNG:
1. Gửi HTTP request tới API/trang web của congbobanan.toaan.gov.vn
2. Parse HTML/JSON để lấy toàn văn bản án
3. Lưu vào SQLite database (legal_theory_mind.db)
4. Index vào FTS5 cho full-text search

GHI CHÚ TRUNG THỰC:
- Script này thực sự gửi HTTP request qua Internet
- Nếu trang web chặn hoặc thay đổi cấu trúc, script sẽ báo lỗi rõ ràng
- Mỗi request có delay 2-3 giây để không quá tải server
"""

import os
import sys
import json
import time
import sqlite3
import logging
import hashlib
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("RealCrawler")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

# Kiểm tra thư viện cần thiết
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# ============================================================
# NGUỒN 1: congbobanan.toaan.gov.vn - Cổng Công bố Bản án
# ============================================================

COURT_SEARCH_URL = "https://congbobanan.toaan.gov.vn/0tat1cvn/ban-an-quyet-dinh"
COURT_API_URL = "https://congbobanan.toaan.gov.vn/api/ban-an"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def ensure_db_tables():
    """Đảm bảo các bảng cần thiết tồn tại."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Bảng lưu bản án thật
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_court_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number TEXT,
        court_name TEXT,
        case_type TEXT,
        decision_date TEXT,
        full_text TEXT,
        url TEXT UNIQUE,
        word_count INTEGER,
        crawled_at TEXT,
        content_hash TEXT UNIQUE
    )
    """)
    
    # Bảng lưu văn bản pháp luật thật
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_legal_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_number TEXT,
        doc_type TEXT,
        issuing_body TEXT,
        issue_date TEXT,
        title TEXT,
        full_text TEXT,
        url TEXT UNIQUE,
        word_count INTEGER,
        crawled_at TEXT,
        content_hash TEXT UNIQUE
    )
    """)
    
    # Bảng log crawler thật
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_crawler_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT,
        source_url TEXT,
        action TEXT,
        status TEXT,
        details TEXT,
        timestamp TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ Tạo/kiểm tra bảng DB thành công")

def log_crawl_action(source_name, source_url, action, status, details=""):
    """Ghi log mọi hành động crawl thật."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    INSERT INTO real_crawler_logs (source_name, source_url, action, status, details, timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (source_name, source_url, action, status, details, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def crawl_congbobanan():
    """
    Cào bản án từ congbobanan.toaan.gov.vn
    """
    if not HAS_DEPS:
        logger.error("❌ Thiếu thư viện requests và beautifulsoup4!")
        logger.error("   Chạy: pip install requests beautifulsoup4")
        return 0
    
    logger.info("=" * 60)
    logger.info("🏛️  BẮT ĐẦU CÀO THẬT: congbobanan.toaan.gov.vn")
    logger.info("=" * 60)
    
    log_crawl_action("congbobanan.toaan.gov.vn", COURT_SEARCH_URL, "START_CRAWL", "STARTED")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    total_saved = 0
    
    # Thử nhiều cách tiếp cận website
    approaches = [
        # Cách 1: Truy cập trang danh sách bản án
        ("LIST_PAGE", COURT_SEARCH_URL),
        # Cách 2: Thử API endpoint  
        ("API", "https://congbobanan.toaan.gov.vn/api/ban-an?page=1&size=20"),
        # Cách 3: Trang chủ
        ("HOME", "https://congbobanan.toaan.gov.vn"),
        # Cách 4: Sitemap
        ("SITEMAP", "https://congbobanan.toaan.gov.vn/sitemap.xml"),
    ]
    
    for approach_name, url in approaches:
        logger.info(f"\n📡 Thử cách {approach_name}: {url}")
        
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            status_code = resp.status_code
            content_type = resp.headers.get("Content-Type", "")
            content_length = len(resp.content)
            
            logger.info(f"   HTTP Status: {status_code}")
            logger.info(f"   Content-Type: {content_type}")
            logger.info(f"   Content-Length: {content_length} bytes")
            logger.info(f"   Final URL: {resp.url}")
            
            log_crawl_action(
                "congbobanan.toaan.gov.vn", url, 
                f"HTTP_GET_{approach_name}", 
                f"HTTP_{status_code}",
                f"Content-Type: {content_type}, Length: {content_length}"
            )
            
            if status_code == 200:
                if "json" in content_type:
                    # Parse JSON response
                    try:
                        data = resp.json()
                        logger.info(f"   ✅ JSON Response - Keys: {list(data.keys()) if isinstance(data, dict) else f'Array of {len(data)}'}")
                        
                        # Xử lý JSON data
                        items = []
                        if isinstance(data, dict):
                            for key in ["data", "items", "results", "content", "banAns"]:
                                if key in data and isinstance(data[key], list):
                                    items = data[key]
                                    break
                        elif isinstance(data, list):
                            items = data
                        
                        if items:
                            logger.info(f"   📋 Tìm thấy {len(items)} bản án trong JSON")
                            total_saved += process_court_items(items, url)
                        else:
                            logger.info(f"   ℹ️  JSON không chứa danh sách bản án. Cấu trúc: {json.dumps(data, ensure_ascii=False)[:500]}")
                            
                    except json.JSONDecodeError:
                        logger.warning(f"   ⚠️ Không parse được JSON")
                        
                elif "html" in content_type or "xml" in content_type:
                    # Parse HTML
                    soup = BeautifulSoup(resp.content, "html.parser")
                    title = soup.title.string if soup.title else "No title"
                    logger.info(f"   📄 Page Title: {title}")
                    
                    if "xml" in content_type or approach_name == "SITEMAP":
                        # Xử lý sitemap
                        urls = [loc.text for loc in soup.find_all("loc")]
                        logger.info(f"   🗺️  Sitemap: {len(urls)} URLs tìm thấy")
                        if urls:
                            # Lọc URL bản án
                            ban_an_urls = [u for u in urls if "ban-an" in u.lower() or "quyet-dinh" in u.lower()]
                            logger.info(f"   🏛️  URL Bản án: {len(ban_an_urls)}")
                            for ba_url in ban_an_urls[:20]:  # Cào tối đa 20 bản án
                                total_saved += crawl_single_court_page(session, ba_url)
                                time.sleep(2)  # Delay tôn trọng server
                    else:
                        # Parse HTML trang danh sách
                        total_saved += parse_court_list_html(session, soup, resp.url)
                        
            else:
                logger.warning(f"   ⚠️ HTTP {status_code} - Không truy cập được")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"   ❌ Lỗi kết nối: {e}")
            log_crawl_action("congbobanan.toaan.gov.vn", url, f"HTTP_GET_{approach_name}", "CONNECTION_ERROR", str(e)[:200])
        except requests.exceptions.Timeout:
            logger.error(f"   ❌ Timeout sau 30 giây")
            log_crawl_action("congbobanan.toaan.gov.vn", url, f"HTTP_GET_{approach_name}", "TIMEOUT", "30s timeout")
        except Exception as e:
            logger.error(f"   ❌ Lỗi không xác định: {e}")
            log_crawl_action("congbobanan.toaan.gov.vn", url, f"HTTP_GET_{approach_name}", "ERROR", str(e)[:200])
        
        time.sleep(3)  # Delay giữa các cách tiếp cận
    
    logger.info(f"\n📊 KẾT QUẢ: Đã lưu {total_saved} bản án THẬT từ congbobanan.toaan.gov.vn")
    log_crawl_action("congbobanan.toaan.gov.vn", COURT_SEARCH_URL, "FINISH_CRAWL", 
                     f"SAVED_{total_saved}", f"Total court decisions saved: {total_saved}")
    
    return total_saved

def parse_court_list_html(session, soup, base_url):
    """Parse trang danh sách bản án HTML."""
    saved = 0
    
    # Tìm các link bản án (nhiều pattern khác nhau)
    link_patterns = [
        {"tag": "a", "class_": lambda c: c and ("ban-an" in str(c).lower() or "detail" in str(c).lower())},
        {"tag": "a", "href": lambda h: h and ("ban-an" in h or "quyet-dinh" in h or "chi-tiet" in h)},
        {"tag": "a", "class_": "title"},
        {"tag": "h3"},
        {"tag": "div", "class_": lambda c: c and "item" in str(c).lower()},
    ]
    
    links_found = []
    
    for pattern in link_patterns:
        tag = pattern.pop("tag")
        elements = soup.find_all(tag, **pattern)
        for el in elements:
            href = el.get("href") if el.name == "a" else None
            if not href:
                # Tìm link con
                link = el.find("a")
                if link:
                    href = link.get("href")
            
            if href:
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                links_found.append(href)
    
    # Deduplicate
    links_found = list(set(links_found))
    logger.info(f"   🔗 Tìm thấy {len(links_found)} links bản án trên trang")
    
    for link in links_found[:30]:  # Tối đa 30 bản án/trang
        saved += crawl_single_court_page(session, link)
        time.sleep(2)
    
    return saved

def crawl_single_court_page(session, url):
    """Cào 1 trang bản án cụ thể."""
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return 0
            
        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Tìm nội dung bản án (nhiều selector khác nhau)
        content_selectors = [
            {"class_": "noi-dung-ban-an"},
            {"class_": "content-detail"},
            {"class_": "detail-content"},
            {"id": "noi-dung"},
            {"class_": "article-content"},
            {"tag": "article"},
        ]
        
        full_text = None
        for selector in content_selectors:
            tag = selector.pop("tag", "div")
            element = soup.find(tag, **selector)
            if element:
                full_text = element.get_text(separator="\n", strip=True)
                break
        
        if not full_text or len(full_text) < 200:
            # Fallback: lấy toàn bộ body text
            body = soup.find("body")
            if body:
                full_text = body.get_text(separator="\n", strip=True)
        
        if not full_text or len(full_text) < 200:
            logger.warning(f"   ⚠️ Không tìm thấy nội dung bản án tại: {url}")
            return 0
        
        # Tìm thông tin metadata
        title = soup.title.string if soup.title else ""
        case_number = extract_case_number(title, full_text)
        court_name = extract_court_name(full_text)
        case_type = classify_case_type(full_text)
        
        # Hash để tránh trùng lặp
        content_hash = hashlib.md5(full_text.encode()).hexdigest()
        word_count = len(full_text.split())
        
        # Lưu vào DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
            INSERT OR IGNORE INTO real_court_decisions 
            (case_number, court_name, case_type, decision_date, full_text, url, word_count, crawled_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_number, court_name, case_type, "", full_text, url, word_count, datetime.now().isoformat(), content_hash))
            
            if c.rowcount > 0:
                # Index vào FTS
                row_id = c.lastrowid
                c.execute("""
                INSERT INTO fts_theory (source_table, source_id, title, content, category)
                VALUES ('real_court_decisions', ?, ?, ?, ?)
                """, (row_id, f"Bản án: {case_number}", full_text[:10000], case_type))
                
                conn.commit()
                logger.info(f"   ✅ Lưu bản án: {case_number} | {word_count} từ | {court_name}")
                conn.close()
                return 1
            else:
                logger.info(f"   ℹ️ Bản án đã tồn tại (trùng hash): {url[:80]}")
                conn.close()
                return 0
        except sqlite3.IntegrityError:
            conn.close()
            return 0
        
    except Exception as e:
        logger.error(f"   ❌ Lỗi cào {url[:60]}: {e}")
        return 0

def process_court_items(items, source_url):
    """Xử lý danh sách items từ JSON API."""
    saved = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for item in items:
        # Cố gắng lấy thông tin từ nhiều key khác nhau
        full_text = item.get("noiDung") or item.get("content") or item.get("fullText") or item.get("noi_dung", "")
        case_number = item.get("soBanAn") or item.get("caseNumber") or item.get("so_ban_an", "N/A")
        court_name = item.get("toaAn") or item.get("court") or item.get("toa_an", "N/A")
        case_type = item.get("loaiVuAn") or item.get("caseType") or item.get("loai_vu_an", "N/A")
        decision_date = item.get("ngayTuyenAn") or item.get("date") or item.get("ngay_tuyen_an", "")
        url = item.get("url") or item.get("link") or source_url
        
        if not full_text or len(full_text) < 100:
            continue
        
        content_hash = hashlib.md5(full_text.encode()).hexdigest()
        word_count = len(full_text.split())
        
        try:
            c.execute("""
            INSERT OR IGNORE INTO real_court_decisions 
            (case_number, court_name, case_type, decision_date, full_text, url, word_count, crawled_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_number, court_name, case_type, decision_date, full_text, url, word_count, datetime.now().isoformat(), content_hash))
            
            if c.rowcount > 0:
                row_id = c.lastrowid
                c.execute("""
                INSERT INTO fts_theory (source_table, source_id, title, content, category)
                VALUES ('real_court_decisions', ?, ?, ?, ?)
                """, (row_id, f"Bản án: {case_number}", full_text[:10000], case_type))
                saved += 1
                logger.info(f"   ✅ Lưu: {case_number} | {word_count} từ | {court_name}")
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()
    return saved

def extract_case_number(title, text):
    """Trích xuất số bản án từ tiêu đề hoặc nội dung."""
    import re
    patterns = [
        r'(?:Bản án|Quyết định)?\s*(?:số)?\s*(\d+/\d{4}/\w+-\w+)',
        r'(\d+/\d{4}/(?:HSST|HSPT|DSST|DSPT|KDTM|HC))',
        r'Số:\s*(\S+)',
    ]
    for p in patterns:
        m = re.search(p, title + " " + text[:1000])
        if m:
            return m.group(1)
    return title[:100] if title else "N/A"

def extract_court_name(text):
    """Trích xuất tên tòa án."""
    import re
    patterns = [
        r'(TÒA ÁN NHÂN DÂN[^\.]+)',
        r'(Tòa án nhân dân[^\.]+)',
    ]
    for p in patterns:
        m = re.search(p, text[:500])
        if m:
            return m.group(1).strip()
    return "N/A"

def classify_case_type(text):
    """Phân loại loại vụ án."""
    text_lower = text[:2000].lower()
    if "hình sự" in text_lower:
        return "Hình sự"
    elif "dân sự" in text_lower:
        return "Dân sự"
    elif "hành chính" in text_lower:
        return "Hành chính"
    elif "kinh doanh" in text_lower or "thương mại" in text_lower:
        return "Kinh doanh Thương mại"
    elif "lao động" in text_lower:
        return "Lao động"
    return "Chưa phân loại"


# ============================================================
# NGUỒN 2: thuvienphapluat.vn - Văn bản QPPL
# ============================================================

def crawl_thuvienphapluat():
    """Cào văn bản pháp luật từ thuvienphapluat.vn"""
    if not HAS_DEPS:
        return 0
    
    logger.info("\n" + "=" * 60)
    logger.info("📜 BẮT ĐẦU CÀO THẬT: thuvienphapluat.vn")
    logger.info("=" * 60)
    
    log_crawl_action("thuvienphapluat.vn", "https://thuvienphapluat.vn", "START_CRAWL", "STARTED")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    total_saved = 0
    
    # Các URL quan trọng
    urls_to_try = [
        ("BOLUAT", "https://thuvienphapluat.vn/van-ban/Bo-luat/Bo-luat-Hinh-su-2015-296661.aspx"),
        ("BOLUAT_DS", "https://thuvienphapluat.vn/van-ban/Bo-luat/Bo-luat-Dan-su-2015-296215.aspx"),
        ("LUAT_DDAI", "https://thuvienphapluat.vn/van-ban/Bat-dong-san/Luat-Dat-dai-2024-415831.aspx"),
        ("SEARCH", "https://thuvienphapluat.vn/page/tim-van-ban.aspx?keyword=bộ+luật&area=0&type=0&match=True&eff=3&page=1"),
        ("HOME", "https://thuvienphapluat.vn"),
    ]
    
    for label, url in urls_to_try:
        logger.info(f"\n📡 Thử [{label}]: {url[:80]}...")
        
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            logger.info(f"   HTTP Status: {resp.status_code} | Content-Length: {len(resp.content)}")
            
            log_crawl_action("thuvienphapluat.vn", url, f"HTTP_GET_{label}", f"HTTP_{resp.status_code}",
                           f"Length: {len(resp.content)}")
            
            if resp.status_code == 200 and "html" in resp.headers.get("Content-Type", ""):
                soup = BeautifulSoup(resp.content, "html.parser")
                title = soup.title.string if soup.title else "No title"
                logger.info(f"   📄 Title: {title}")
                
                # Tìm nội dung văn bản pháp luật
                content_selectors = [
                    {"class_": "content1"},
                    {"class_": "toanvancontent"},
                    {"class_": "fulltext"},
                    {"id": "toanvancontent"},
                    {"id": "divContent"},
                    {"class_": "noidung"},
                ]
                
                full_text = None
                for selector in content_selectors:
                    element = soup.find("div", **selector)
                    if element:
                        full_text = element.get_text(separator="\n", strip=True)
                        break
                
                if full_text and len(full_text) > 500:
                    content_hash = hashlib.md5(full_text.encode()).hexdigest()
                    word_count = len(full_text.split())
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    try:
                        c.execute("""
                        INSERT OR IGNORE INTO real_legal_documents
                        (doc_number, doc_type, issuing_body, issue_date, title, full_text, url, word_count, crawled_at, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, ("", label, "", "", title, full_text, url, word_count, datetime.now().isoformat(), content_hash))
                        
                        if c.rowcount > 0:
                            row_id = c.lastrowid
                            c.execute("""
                            INSERT INTO fts_theory (source_table, source_id, title, content, category)
                            VALUES ('real_legal_documents', ?, ?, ?, ?)
                            """, (row_id, title, full_text[:10000], label))
                            conn.commit()
                            total_saved += 1
                            logger.info(f"   ✅ Lưu VBPL: {title[:60]} | {word_count} từ")
                    except sqlite3.IntegrityError:
                        logger.info(f"   ℹ️  Đã tồn tại")
                    finally:
                        conn.close()
                else:
                    if full_text:
                        logger.info(f"   ℹ️  Nội dung quá ngắn: {len(full_text)} chars")
                    else:
                        logger.info(f"   ℹ️  Không tìm thấy vùng nội dung văn bản")
                        # Log cấu trúc HTML để debug
                        divs = soup.find_all("div", id=True)
                        logger.info(f"   📐 Divs with IDs: {[d.get('id') for d in divs[:10]]}")
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"   ❌ Lỗi kết nối: {str(e)[:100]}")
            log_crawl_action("thuvienphapluat.vn", url, f"HTTP_GET_{label}", "CONNECTION_ERROR", str(e)[:200])
        except Exception as e:
            logger.error(f"   ❌ Lỗi: {str(e)[:100]}")
            log_crawl_action("thuvienphapluat.vn", url, f"HTTP_GET_{label}", "ERROR", str(e)[:200])
        
        time.sleep(3)
    
    logger.info(f"\n📊 KẾT QUẢ: Đã lưu {total_saved} văn bản pháp luật THẬT từ thuvienphapluat.vn")
    log_crawl_action("thuvienphapluat.vn", "https://thuvienphapluat.vn", "FINISH_CRAWL",
                     f"SAVED_{total_saved}", f"Total legal docs saved: {total_saved}")
    
    return total_saved


# ============================================================
# MAIN
# ============================================================

def main():
    logger.info("=" * 70)
    logger.info("🌐 DATALUATVN - CÀO DỮ LIỆU THẬT TỪ INTERNET")
    logger.info("   Đây là script cào THẬT, gửi HTTP request qua mạng.")
    logger.info("   Không fake, không synthetic, không mô phỏng.")
    logger.info("=" * 70)
    
    if not HAS_DEPS:
        logger.error("❌ CẦN CÀI THƯ VIỆN: pip install requests beautifulsoup4")
        sys.exit(1)
    
    # Tạo bảng
    ensure_db_tables()
    
    # Cào từ nhiều nguồn
    total = 0
    total += crawl_congbobanan()
    total += crawl_thuvienphapluat()
    
    # Báo cáo tổng kết
    logger.info("\n" + "=" * 70)
    logger.info("📊 BÁO CÁO TỔNG KẾT CÀO DỮ LIỆU THẬT")
    logger.info("=" * 70)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM real_court_decisions")
    court_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM real_legal_documents")
    doc_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM real_crawler_logs")
    log_count = c.fetchone()[0]
    
    logger.info(f"  🏛️  Bản án THẬT: {court_count}")
    logger.info(f"  📜 Văn bản QPPL THẬT: {doc_count}")
    logger.info(f"  📝 Crawler logs: {log_count}")
    logger.info(f"  💾 Tổng tài liệu mới: {total}")
    
    # In chi tiết logs
    c.execute("SELECT source_name, action, status, details, timestamp FROM real_crawler_logs ORDER BY id")
    for row in c.fetchall():
        logger.info(f"  LOG: [{row[4][:19]}] {row[0]} | {row[1]} | {row[2]} | {row[3][:80]}")
    
    conn.close()
    
    if total == 0:
        logger.warning("\n⚠️  KHÔNG CÀO ĐƯỢC DỮ LIỆU NÀO.")
        logger.warning("   Nguyên nhân có thể:")
        logger.warning("   1. Website chặn request (cần VPN hoặc proxy)")
        logger.warning("   2. Website thay đổi cấu trúc HTML")  
        logger.warning("   3. Lỗi kết nối mạng")
        logger.warning("   Kiểm tra real_crawler_logs trong DB để biết chi tiết.")

if __name__ == "__main__":
    main()
