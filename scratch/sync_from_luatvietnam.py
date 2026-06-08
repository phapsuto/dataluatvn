import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set project path
sys.path.insert(0, "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam")

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def clean_label(text):
    text = text.replace(":", "")
    text = re.sub(r'\s*ⓘ\s*', '', text)
    text = text.split('(')[0].strip()
    return text

def get_next_doc_id():
    conn = sqlite3.connect(DB_NAME)
    max_id = conn.execute("SELECT MAX(id) FROM documents").fetchone()[0] or 0
    conn.close()
    return max_id + 1

def fetch_document_detail(doc_url):
    full_url = "https://luatvietnam.vn" + doc_url if doc_url.startswith("/") else doc_url
    try:
        resp = requests.get(full_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Parse metadata table
        meta = {}
        table = soup.find('table', class_='table-bordered') or soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                i = 0
                while i < len(cells) - 1:
                    lbl_cell = cells[i]
                    val_cell = cells[i+1]
                    lbl_text = clean_label(lbl_cell.get_text(strip=True))
                    val_text = val_cell.get_text(strip=True)
                    if lbl_text:
                        meta[lbl_text] = val_text
                    i += 2
        
        # Parse content div
        noidung_div = soup.find(id='noidung') or soup.find(class_='tab-noi-dung')
        content_html = ""
        if noidung_div:
            # Check if it has real content
            txt = noidung_div.get_text(strip=True)
            if "đăng nhập" not in txt.lower() and "đang cập nhật nội dung" not in txt.lower() and len(txt) > 200:
                content_html = str(noidung_div)
        
        # Fallback content if empty or restricted
        so_ky_hieu = meta.get("Số hiệu", "")
        co_quan = meta.get("Cơ quan ban hành", "")
        ngay_bh = meta.get("Ngày ban hành", "")
        ngay_hl = meta.get("Ngày có hiệu lực", meta.get("Ngày áp dụng", meta.get("Áp dụng", "")))
        linh_vuc = meta.get("Lĩnh vực", "")
        tinh_trang = meta.get("Tình trạng hiệu lực", "")
        trich_yeu = meta.get("Trích yếu", "")
        
        if not content_html:
            content_html = f"""
            <div id="content" class="noi-dung">
              <h2 style="color: #0f2c59; font-family: var(--font-ui); font-weight: 700; margin-bottom: 1rem;">{soup.title.string if soup.title else "Thông tin văn bản"}</h2>
              <div style="background: rgba(15, 44, 89, 0.03); border-left: 4px solid #b8956c; padding: 1.25rem; margin-bottom: 1.5rem; border-radius: 6px; font-family: var(--font-ui); line-height: 1.6;">
                <p style="margin-bottom: 0.5rem;"><strong>Cơ quan ban hành:</strong> {co_quan or 'Đang cập nhật'}</p>
                <p style="margin-bottom: 0.5rem;"><strong>Số hiệu:</strong> {so_ky_hieu or 'Đang cập nhật'}</p>
                <p style="margin-bottom: 0.5rem;"><strong>Ngày ban hành:</strong> {ngay_bh or 'Đang cập nhật'}</p>
                <p style="margin-bottom: 0.5rem;"><strong>Ngày có hiệu lực:</strong> {ngay_hl or 'Đang cập nhật'}</p>
                <p style="margin-bottom: 0.5rem;"><strong>Lĩnh vực:</strong> {linh_vuc or 'Đang cập nhật'}</p>
                <p style="margin-bottom: 0.5rem;"><strong>Tình trạng hiệu lực:</strong> <span style="color: #dc2626; font-weight: 700;">{tinh_trang or 'Còn hiệu lực'}</span></p>
              </div>
              <p style="font-family: var(--font-doc); font-size: 1.05rem; line-height: 1.7; color: #334155; margin-bottom: 1rem;"><strong>Tóm tắt nội dung:</strong> {trich_yeu or 'Nội dung tóm tắt văn bản đang được cập nhật...'}</p>
              <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 1.25rem; text-align: center; margin-top: 2rem; font-family: var(--font-ui);">
                <p style="color: #64748b; margin-bottom: 1rem;">Nội dung toàn văn bản Word đang được cập nhật. Quý khách có thể sử dụng tính năng tải file Word (.docx) ở góc phải để tải bản soạn thảo chính thức.</p>
              </div>
            </div>
            """
            
        return {
            "meta": meta,
            "content_html": content_html
        }
    except Exception as e:
        print(f"Error fetching detail {doc_url}: {e}")
        return None

def main():
    print("=" * 60)
    print("🔄 CẬP NHẬT DỮ LIỆU LUẬT MỚI NHẤT TỪ LUATVIETNAM.VN")
    print("=" * 60)
    
    # 1. Get existing documents to check for duplicates
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    existing_docs = set()
    cursor = conn.cursor()
    cursor.execute("SELECT so_ky_hieu, title FROM documents")
    for row in cursor.fetchall():
        if row['so_ky_hieu']:
            existing_docs.add(row['so_ky_hieu'].strip().lower())
        if row['title']:
            existing_docs.add(row['title'].strip().lower())
    conn.close()
    
    print(f"📚 Đang có {len(existing_docs):,} ký hiệu / tiêu đề văn bản trong DB.")
    
    # 2. Page loop to find new documents in 2026
    new_docs = []
    # Fetch top 15 pages (covers May and late April 2026)
    pages_to_crawl = 20
    print(f"🔍 Quét {pages_to_crawl} trang danh sách văn bản mới 2026...")
    
    for page in range(1, pages_to_crawl + 1):
        url = f"https://luatvietnam.vn/van-ban/tim-van-ban.html?SearchKeyword=&Year=2026&PageSize=20&PageIndex={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Lỗi tải trang {page}")
                continue
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            docs = soup.find_all(class_='post-doc')
            print(f"   Trang {page}: tìm thấy {len(docs)} văn bản.")
            
            for doc in docs:
                title_tag = doc.find('h2', class_='doc-title')
                if not title_tag:
                    continue
                a_tag = title_tag.find('a')
                if not a_tag:
                    continue
                
                title = a_tag.get_text(strip=True)
                href = a_tag['href']
                
                # Extract number using regex or from title
                # E.g. "Quyết định 52/2026/QĐ-UBND..." -> number is 52/2026/QĐ-UBND
                # Often title starts with document type and number
                # Let's extract "số X/Y/Z" or "số X/Y" or "X/Y/Z"
                so_hieu = ""
                m = re.search(r'(\d+/\d{4}/[A-ZĐa-zđ\-]+)', title)
                if m:
                    so_hieu = m.group(1)
                else:
                    # try other patterns
                    m = re.search(r'(?:số|Quyết định|Thông tư|Nghị định)\s*(\d+(?:/\d+)*[\w\-]+)', title, re.IGNORECASE)
                    if m:
                        so_hieu = m.group(1)
                
                # Extract date from meta
                ngay_bh = ""
                meta_div = doc.find(class_='post-meta-doc')
                if meta_div:
                    dmy_divs = meta_div.find_all(class_='doc-dmy')
                    for dmy in dmy_divs:
                        lbl_span = dmy.find(class_='w-doc-dmy1')
                        val_span = dmy.find(class_='w-doc-dmy2')
                        if lbl_span and val_span and 'Ban hành' in lbl_span.get_text():
                            ngay_bh = val_span.get_text(strip=True)
                            break
                
                # Check duplicates
                clean_so_hieu = so_hieu.strip().lower() if so_hieu else ""
                clean_title = title.strip().lower()
                
                is_dup = False
                if clean_so_hieu and clean_so_hieu in existing_docs:
                    is_dup = True
                elif clean_title in existing_docs:
                    is_dup = True
                    
                if not is_dup:
                    new_docs.append({
                        "title": title,
                        "so_ky_hieu": so_hieu,
                        "ngay_ban_hanh": ngay_bh,
                        "href": href
                    })
        except Exception as e:
            print(f"❌ Lỗi quét trang {page}: {e}")
            
    print(f"\n✨ Tìm thấy {len(new_docs)} văn bản mới chưa có trong DB.")
    if not new_docs:
        print("✅ Dữ liệu đã là mới nhất! Không có gì cần cập nhật.")
        return
        
    # 3. Fetch details for new documents in parallel
    print(f"📥 Đang tải chi tiết cho {len(new_docs)} văn bản mới (hỗ trợ đa luồng)...")
    
    # Store fetched detail pages
    detailed_docs = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_doc = {executor.submit(fetch_document_detail, doc["href"]): doc for doc in new_docs}
        for idx, future in enumerate(as_completed(future_to_doc)):
            doc = future_to_doc[future]
            res = future.result()
            if res:
                doc.update(res)
                detailed_docs.append(doc)
            print(f"   ⏳ [{idx+1}/{len(new_docs)}] Đã tải: {doc['title'][:60]}...")
            
    # 4. Save to databases
    print(f"\n🔄 Đang lưu {len(detailed_docs)} văn bản mới vào SQLite...")
    
    conn_main = sqlite3.connect(DB_NAME, timeout=30.0)
    conn_main.execute("PRAGMA journal_mode=WAL")
    conn_main.execute("PRAGMA synchronous=NORMAL")
    
    conn_content = sqlite3.connect(CONTENT_DB, timeout=30.0)
    conn_content.execute("PRAGMA journal_mode=WAL")
    conn_content.execute("PRAGMA synchronous=NORMAL")
    
    next_id = get_next_doc_id()
    saved_count = 0
    
    for doc in detailed_docs:
        meta = doc.get("meta", {})
        
        title = doc["title"]
        so_ky_hieu = doc["so_ky_hieu"] or meta.get("Số hiệu", "")
        ngay_bh = doc["ngay_ban_hanh"] or meta.get("Ngày ban hành", "")
        loai_vb = meta.get("Loại văn bản", "")
        co_quan = meta.get("Cơ quan ban hành", "")
        linh_vuc = meta.get("Lĩnh vực", "")
        nguoi_ky = meta.get("Người ký", "")
        ngay_hl = meta.get("Ngày có hiệu lực", meta.get("Ngày áp dụng", meta.get("Áp dụng", "")))
        ngay_het_hl = meta.get("Ngày hết hiệu lực", "")
        ngay_dang_cb = meta.get("Ngày đăng công báo", "")
        so_dang_cb = meta.get("Số công báo", "")
        tinh_trang = meta.get("Tình trạng hiệu lực", "Còn hiệu lực")
        content_html = doc.get("content_html", "")
        
        # Clean placeholders
        if "đã biết" in ngay_hl.lower(): ngay_hl = ngay_bh
        if "đang cập nhật" in ngay_het_hl.lower(): ngay_het_hl = ""
        if "đang cập nhật" in ngay_dang_cb.lower(): ngay_dang_cb = ""
        if "đang cập nhật" in so_dang_cb.lower(): so_dang_cb = ""
        
        # Determine document ID
        doc_id = next_id
        next_id += 1
        
        # Insert main document
        try:
            conn_main.execute("""
                INSERT INTO documents (
                    id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban,
                    ngay_co_hieu_luc, ngay_het_hieu_luc, nguon_thu_thap,
                    ngay_dang_cong_bao, nganh, linh_vuc, co_quan_ban_hanh,
                    nguoi_ky, thong_tin_ap_dung, tinh_trang_hieu_luc, has_content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, title, so_ky_hieu, ngay_bh, loai_vb,
                ngay_hl, ngay_het_hl, "luatvietnam",
                ngay_dang_cb, linh_vuc, linh_vuc, co_quan,
                nguoi_ky, so_dang_cb, tinh_trang, 1 if content_html else 0
            ))
            
            # Insert content
            if content_html:
                conn_content.execute(
                    "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
                    (doc_id, content_html)
                )
                
            # Insert FTS
            conn_main.execute(
                "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
                (doc_id, title, so_ky_hieu)
            )
            
            saved_count += 1
        except Exception as e:
            print(f"❌ Lỗi khi lưu văn bản {so_ky_hieu}: {e}")
            
    conn_main.commit()
    conn_content.commit()
    
    conn_main.close()
    conn_content.close()
    
    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH ĐỒNG BỘ DỮ LIỆU LUẬT VIỆT NAM!")
    print(f"   ✅ Đã lưu mới thành công: {saved_count} văn bản pháp luật.")
    print("=" * 60)

if __name__ == "__main__":
    main()
