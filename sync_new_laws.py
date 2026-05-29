import os
import re
import sys
import time
import sqlite3
import requests
from bs4 import BeautifulSoup

# --- Configuration ---
DB_NAME = "vietnamese_legal_documents.db"
LOG_NAME = "sync.log"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg)
    with open(LOG_NAME, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def get_latest_date_in_db():
    """Finds the latest publication date (dd/MM/yyyy) in the SQLite database"""
    if not os.path.exists(DB_NAME):
        return None
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # SQLite sortable date expression for dd/MM/yyyy format: yyyy-MM-dd
    sortable_date_expr = "substr(ngay_ban_hanh, 7, 4) || '-' || substr(ngay_ban_hanh, 4, 2) || '-' || substr(ngay_ban_hanh, 1, 2)"
    
    query = f"""
    SELECT ngay_ban_hanh 
    FROM documents 
    WHERE ngay_ban_hanh != '' 
      AND ngay_ban_hanh LIKE '__/__/____' 
    ORDER BY {sortable_date_expr} DESC 
    LIMIT 1;
    """
    
    try:
        cursor.execute(query)
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        log(f"⚠️ Error getting latest date from DB: {e}")
        return None
    finally:
        conn.close()

def parse_item_id_from_url(url):
    """Extracts ItemID from vbpl.vn detail URL"""
    m = re.search(r"ItemID=(\d+)", url)
    return int(m.group(1)) if m else None

def extract_so_hieu(text):
    """Extracts Vietnamese legal document reference code (so_ky_hieu) from text"""
    m = re.search(r"(\d{1,4}/\d{4}/[A-ZĐ\d][\w\-Đđ]+)", text)
    return m.group(1) if m else None

def fetch_document_content(item_id):
    """Downloads and extracts full-text HTML content of a document from vbpl.vn"""
    url = f"https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID={item_id}"
    log(f"📥 Fetching full text for ItemID {item_id}...")
    
    # Retries for reliability
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                
                # Check known content selectors on vbpl.vn
                content_selectors = [
                    ".vbpq-content", 
                    "#ctl00_PlaceHolderMain_ctl01__ControlWrapper_RichHtmlField",
                    ".noi-dung-vb",
                    "article",
                    "#content"
                ]
                
                content_html = None
                for sel in content_selectors:
                    el = soup.select_one(sel)
                    if el:
                        content_html = str(el)
                        break
                        
                if not content_html:
                    content_html = str(soup.body) # Fallback to body
                    
                return content_html
            else:
                log(f"   ⚠️ Request failed (Attempt {attempt+1}/3), Status: {r.status_code}")
        except Exception as e:
            log(f"   ⚠️ Network error (Attempt {attempt+1}/3): {e}")
            
        time.sleep(2)
        
    return None

def sync_new_laws():
    log("============================================================")
    log("🚀 RUNNING INCREMENTAL LEGAL DATA SYNC PIPELINE")
    log("============================================================")
    
    latest_db_date = get_latest_date_in_db()
    log(f"📅 Latest document date currently in Database: {latest_db_date or 'No date found'}")
    
    # Target URL for newly published documents (sorted by publish date descending)
    search_url = "https://vbpl.vn/TW/Pages/vbpq-tim-kiem.aspx?Keyword=&sXepLoai=NgayBanHanh&PageIndex=1"
    
    log(f"🔍 Queting vbpl.vn for new documents...")
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            log(f"❌ Failed to reach vbpl.vn: Status {r.status_code}")
            return
    except Exception as e:
        log(f"❌ Network error connecting to vbpl.vn: {e}")
        return
        
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Parse documents list from the page
    # Common vbpl selectors for list items
    items = soup.select(".vbpq-item, .list-result li, .search-result .item")
    if not items:
        # Fallback to general list of links
        items = [a.parent for a in soup.select("a.title, a.vbpq-title, h3 a")]
        
    log(f"📊 Found {len(items)} documents on the first page of search results.")
    
    if not items:
        log("⚠️ No list items could be parsed. The HTML structure of the site might have changed.")
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    new_docs_count = 0
    
    for item in items:
        try:
            # Find the title and URL link
            link_el = item.select_one("a.title, a.vbpq-title, h3 a, a")
            if not link_el:
                continue
                
            title = link_el.text.strip()
            href = link_el.get("href", "")
            if not title or not href:
                continue
                
            full_url = href if href.startswith("http") else f"https://vbpl.vn{href}"
            item_id = parse_item_id_from_url(full_url)
            if not item_id:
                continue
                
            # Check if document already exists in DB
            cursor.execute("SELECT 1 FROM documents WHERE id = ?", (item_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Document already exists, skip
                continue
                
            log(f"✨ New Document Detected! ID: {item_id} | Title: {title[:80]}...")
            
            # Extract metadata from the list item element
            so_hieu = item.select_one(".so-hieu, .code")
            so_hieu = so_hieu.text.strip() if so_hieu else extract_so_hieu(item.text) or ""
            
            loai_vb = item.select_one(".loai-vb, .type")
            loai_vb = loai_vb.text.strip() if loai_vb else "Văn bản pháp luật"
            
            co_quan = item.select_one(".co-quan, .organ")
            co_quan = co_quan.text.strip() if co_quan else ""
            
            ngay_ban_hanh = item.select_one(".date, .ngay-ban-hanh")
            ngay_ban_hanh = ngay_ban_hanh.text.strip() if ngay_ban_hanh else ""
            
            tinh_trang = item.select_one(".hieu-luc, .status")
            tinh_trang = tinh_trang.text.strip() if tinh_trang else "Còn hiệu lực"
            
            # Fetch full-text HTML content
            content_html = fetch_document_content(item_id)
            if not content_html:
                log(f"   ⚠️ Could not download content for ID {item_id}. Skipping...")
                continue
                
            # Insert into database
            cursor.execute("""
            INSERT OR REPLACE INTO documents (
                id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, 
                co_quan_ban_hanh, tinh_trang_hieu_luc, content_html
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item_id, title, so_hieu, ngay_ban_hanh, loai_vb, co_quan, tinh_trang, content_html))
            conn.commit()
            
            new_docs_count += 1
            log(f"   ✅ Successfully added ID {item_id} to SQLite DB!")
            
            # Throttle requests to avoid getting rate-limited
            time.sleep(1.5)
            
        except Exception as item_err:
            log(f"⚠️ Error processing item: {item_err}")
            
    conn.close()
    
    log("============================================================")
    log(f"🎉 SYNC COMPLETED: {new_docs_count} new laws added to database.")
    log("============================================================")

if __name__ == "__main__":
    sync_new_laws()
