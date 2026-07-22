import os
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from app.routers.laws import smart_search_laws
from app.utils.graph_retrieval import graph_expand_results
from app.database import get_db_connection

def parse_db_date(date_str: str) -> str:
    """Converts dd/mm/yyyy to yyyy-mm-dd for chronological sorting."""
    if not date_str or len(date_str) < 10:
        return "0000-00-00"
    parts = date_str.split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return "0000-00-00"

def strip_accents_and_lowercase(text: str) -> str:
    """Removes Vietnamese accents and converts to lowercase for robust matching."""
    if not text:
        return ""
    text = text.lower()
    import unicodedata
    text = unicodedata.normalize('NFD', text)
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = text.replace('đ', 'd').replace('Đ', 'D')
    return text




_FPT_RERANK_SEMAPHORE = None

def get_fpt_rerank_semaphore():
    global _FPT_RERANK_SEMAPHORE
    import asyncio
    if _FPT_RERANK_SEMAPHORE is None:
        _FPT_RERANK_SEMAPHORE = asyncio.Semaphore(3)  # Limit concurrent FPT Rerank API calls to 3
    return _FPT_RERANK_SEMAPHORE

async def ultimate_retrieve(
    query: str, 
    domain_filter: List[str] = None, 
    top_k: int = 5,
    extracted_year: Optional[int] = None,
    extracted_doc_type: Optional[str] = None,
    extracted_issuer: Optional[str] = None,
    query_vector: Optional[Any] = None
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Pipeline retrieval: Exact Match → Smart Search (FTS5 + FAISS + RRF) → Graph Expansion → Rerank.
    Returns formatted chunks string and citation_map dict.
    """
    # Normalize query spaces (e.g. "34 / 2011" -> "34/2011")
    query_norm_spaces = re.sub(r'\s*/\s*', '/', query)
    query_norm_spaces = re.sub(r'\s*-\s*', '-', query_norm_spaces)

    # Auto-extract metadata if not explicitly provided (crucial for FLARE active searches)
    if extracted_year is None:
        year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})[-/]', query_norm_spaces)
        if not year_in_symbol_match:
            year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})[-/][A-ZĐđ]', query)
        if not year_in_symbol_match:
            year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})-[A-ZĐđ]', query)
        if not year_in_symbol_match:
            year_in_symbol_match = re.search(r'\b\d+/((?:19|20)\d{2})\b', query)
            
        if year_in_symbol_match:
            extracted_year = int(year_in_symbol_match.group(1))
        else:
            if not re.search(r'(nhiệm kỳ|giai đoạn|kế hoạch)\s+\d+', query.lower()):
                year_word_match = re.search(r'\bnăm\s+((?:19|20)\d{2})\b', query.lower())
                if year_word_match:
                    extracted_year = int(year_word_match.group(1))
                    
    if extracted_doc_type is None:
        query_lower = query.lower()
        if "hiến pháp" in query_lower:
            extracted_doc_type = "Hiến pháp"
        elif "bộ luật" in query_lower:
            extracted_doc_type = "Bộ luật"
        elif "luật" in query_lower:
            exclude_words = ["pháp luật", "điều luật", "luật sư", "luật pháp", "kỷ luật", "tiền lệ luật"]
            if not any(ew in query_lower for ew in exclude_words):
                extracted_doc_type = "Luật"
        elif "nghị định" in query_lower:
            extracted_doc_type = "Nghị định"
        elif "thông tư liên tịch" in query_lower:
            extracted_doc_type = "Thông tư liên tịch"
        elif "thông tư" in query_lower:
            extracted_doc_type = "Thông tư"
        elif "quyết định" in query_lower:
            extracted_doc_type = "Quyết định"
        elif "nghị quyết" in query_lower:
            extracted_doc_type = "Nghị quyết"
        elif "pháp lệnh" in query_lower:
            extracted_doc_type = "Pháp lệnh"
        elif "chỉ thị" in query_lower:
            extracted_doc_type = "Chỉ thị"

    if extracted_issuer is None:
        query_lower = query.lower()
        
        # ── Priority: "do X ban hành" pattern (most reliable for D-type queries) ──
        do_ban_hanh = re.search(r'do\s+(.+?)\s+ban\s+hành', query, re.IGNORECASE)
        if do_ban_hanh:
            raw_issuer = do_ban_hanh.group(1).strip()
            # Chỉ dùng nếu issuer có ít nhất 2 từ (loại bỏ false positive)
            if len(raw_issuer.split()) >= 2:
                extracted_issuer = raw_issuer
        
        if not extracted_issuer:
            if "chính phủ" in query_lower:
                extracted_issuer = "Chính phủ"
            elif "thủ tướng" in query_lower:
                extracted_issuer = "Thủ tướng Chính phủ"
            elif "bộ tài chính" in query_lower:
                extracted_issuer = "Bộ Tài chính"
            elif "bộ y tế" in query_lower:
                extracted_issuer = "Bộ Y tế"
            elif "bộ công thương" in query_lower:
                extracted_issuer = "Bộ Công thương"
            elif "bộ giáo dục" in query_lower or "bộ gd&đt" in query_lower or "bộ gd-đt" in query_lower:
                extracted_issuer = "Bộ Giáo dục và Đào tạo"
            elif "bộ lao động" in query_lower or "bộ ldtbxh" in query_lower or "bộ lđtbxh" in query_lower or "thương binh và xã hội" in query_lower:
                extracted_issuer = "Bộ Lao động - Thương binh và Xã hội"
            elif "bộ công an" in query_lower:
                extracted_issuer = "Bộ Công an"
            elif "bộ quốc phòng" in query_lower:
                extracted_issuer = "Bộ Quốc phòng"
            elif "bộ tư pháp" in query_lower:
                extracted_issuer = "Bộ Tư pháp"
            elif "bộ xây dựng" in query_lower:
                extracted_issuer = "Bộ Xây dựng"
            elif "bộ giao thông" in query_lower or "bộ gtvt" in query_lower:
                extracted_issuer = "Bộ Giao thông vận tải"
            elif "bộ kế hoạch" in query_lower or "bộ kh&đt" in query_lower or "bộ kh-đt" in query_lower:
                extracted_issuer = "Bộ Kế hoạch và Đầu tư"
            elif "bộ tài nguyên" in query_lower or "bộ tn&mt" in query_lower or "bộ tn-mt" in query_lower:
                extracted_issuer = "Bộ Tài nguyên và Môi trường"
            elif "bộ thông tin" in query_lower or "bộ tt&tt" in query_lower or "bộ tt-tt" in query_lower:
                extracted_issuer = "Bộ Thông tin và Truyền thông"
            elif "bộ nông nghiệp" in query_lower or "bộ nn&ptnt" in query_lower or "bộ nn-ptnt" in query_lower:
                extracted_issuer = "Bộ Nông nghiệp và Phát triển nông thôn"
            elif "quốc hội" in query_lower:
                extracted_issuer = "Quốc hội"
            elif "ủy ban thường vụ quốc hội" in query_lower or "ubtvqh" in query_lower:
                extracted_issuer = "Ủy ban Thường vụ Quốc hội"
            elif "tòa án nhân dân tối cao" in query_lower or "tandtc" in query_lower:
                extracted_issuer = "Tòa án nhân dân tối cao"
        if not extracted_issuer:
            local_match = re.search(
                r'((?:ubnd|hđnd|ủy ban nhân dân|hội đồng nhân dân)\s+(?:tỉnh|thành phố|quận|huyện|thị xã)\s+[A-ZĐđÀ-ỹ0-9][a-zđà-ỹ0-9]*(\s+[A-ZĐđÀ-ỹ0-9][a-zđà-ỹ0-9]*)*)',
                query,
                flags=re.IGNORECASE
            )
            if local_match:
                full_match = local_match.group(1).strip()
                full_match = re.sub(r'\s+(?:ban|quy|có|nội|về|thuộc|nằm|trích|đọc)\b.*$', '', full_match, flags=re.IGNORECASE).strip()
                full_match_lower = full_match.lower()
                if full_match_lower.startswith("ubnd"):
                    full_match = "Ủy ban nhân dân" + full_match[4:]
                elif full_match_lower.startswith("hđnd"):
                    full_match = "Hội đồng nhân dân" + full_match[4:]
                extracted_issuer = full_match

    # ── Step 0: EXACT MATCH BOOST ──
    # Nếu query chứa số hiệu VB cụ thể → fetch trực tiếp từ DB và inject vào pool
    exact_chunks = []
    # Chuẩn hóa query trước khi extract symbol: loại bỏ prefix, space thừa, dấu chấm cuối
    query_for_symbol = re.sub(r'(?:Nghị quyết|Quyết định|Thông tư|Nghị định)\s+số\s+', '', query_norm_spaces)
    query_for_symbol = re.sub(r'\bSố:\s*', '', query_for_symbol)
    query_for_symbol = re.sub(r'\s+/', '/', query_for_symbol)  # "05 /2020" → "05/2020"
    query_for_symbol = re.sub(r'/\s+', '/', query_for_symbol)  # Ngược lại
    query_for_symbol = re.sub(r'\s*-\s*', '-', query_for_symbol)  # "QĐ - UBND" → "QĐ-UBND"
    query_for_symbol = re.sub(r'\s*\([^)]*\)\s*', ' ', query_for_symbol).strip()  # "(c)", "(XÓA)" → remove
    query_for_symbol = query_for_symbol.replace("'", "").replace('"', '')  # Strip quotes before regex
    so_ky_hieu_match = re.search(
        r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|\b\d+-[A-Za-zĐđÀ-ỹ]{2,}\b)',
        query_for_symbol
    )
    dieu_match = re.search(r'[Đđ]iều\s+(\d+)', query)
    
    if so_ky_hieu_match:
        so_hieu = so_ky_hieu_match.group(0).strip().rstrip('.')  # "11/2012/NQ-HĐND." → no dot
        so_hieu_clean = so_hieu.replace(' ', '').replace("'", "").replace('"', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Step 1: Find the doc_ids from documents table using indexed search
            cursor.execute("SELECT id, title, loai_van_ban, co_quan_ban_hanh, ngay_ban_hanh FROM documents WHERE so_ky_hieu = ?", (so_hieu,))
            rows = cursor.fetchall()
            if not rows:
                # Fallback to whitespace-stripped search (covers documents with messy symbol spaces)
                cursor.execute("SELECT id, title, loai_van_ban, co_quan_ban_hanh, ngay_ban_hanh FROM documents WHERE REPLACE(REPLACE(REPLACE(so_ky_hieu, ' ', ''), \"'\", ''), '\"', '') = ?", (so_hieu_clean,))
                rows = cursor.fetchall()
            if not rows:
                # Fallback: strip parenthetical suffixes like (c), (XÓA) from DB symbol
                so_hieu_no_paren = re.sub(r'\s*\([^)]*\)', '', so_hieu_clean)
                cursor.execute("""
                    SELECT id, title, loai_van_ban, co_quan_ban_hanh, ngay_ban_hanh 
                    FROM documents 
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(so_ky_hieu, ' ', ''), \"'\", ''), '\"', ''), '(c)', '') = ?
                       OR REPLACE(REPLACE(REPLACE(so_ky_hieu, ' ', ''), \"'\", ''), '\"', '') LIKE ? || '%'
                """, (so_hieu_no_paren, so_hieu_no_paren))
                rows = cursor.fetchall()
                
            if rows:
                def norm_agency(val):
                    if not val:
                        return ""
                    val = val.lower()
                    val = re.sub(r'\s+', ' ', val).strip()  # Normalize whitespace
                    val = val.replace("ubnd", "ủy ban nhân dân")
                    val = val.replace("hđnd", "hội đồng nhân dân")
                    return val
                
                scored_docs = []
                
                # ── Fuzzy Locality Matching ──
                # Khi extracted_issuer=None nhưng query chứa tên tỉnh/thành phố,
                # match trực tiếp vào co_quan_ban_hanh để phân biệt trùng số hiệu.
                query_lower_for_loc = query.lower()
                LOCALITIES = [
                    "hà nội", "hồ chí minh", "đà nẵng", "hải phòng", "cần thơ",
                    "an giang", "bà rịa", "vũng tàu", "bắc giang", "bắc kạn", "bạc liêu",
                    "bắc ninh", "bến tre", "bình định", "bình dương", "bình phước",
                    "bình thuận", "cà mau", "cao bằng", "đắk lắk", "đắk nông",
                    "điện biên", "đồng nai", "đồng tháp", "gia lai", "hà giang",
                    "hà nam", "hà tĩnh", "hải dương", "hậu giang", "hòa bình",
                    "hưng yên", "khánh hòa", "kiên giang", "kon tum", "lai châu",
                    "lâm đồng", "lạng sơn", "lào cai", "long an", "nam định",
                    "nghệ an", "ninh bình", "ninh thuận", "phú thọ", "phú yên",
                    "quảng bình", "quảng nam", "quảng ngãi", "quảng ninh", "quảng trị",
                    "sóc trăng", "sơn la", "tây ninh", "thái bình", "thái nguyên",
                    "thanh hóa", "thừa thiên huế", "tiền giang", "trà vinh",
                    "tuyên quang", "vĩnh long", "vĩnh phúc", "yên bái",
                ]
                detected_locality = None
                for loc in LOCALITIES:
                    if loc in query_lower_for_loc:
                        detected_locality = loc
                        break
                
                for r in rows:
                    doc_id, title, loai_van_ban, co_quan_ban_hanh, ngay_ban_hanh = r
                    
                    year_db = None
                    if ngay_ban_hanh and len(ngay_ban_hanh) >= 10:
                        try:
                            year_db = int(ngay_ban_hanh[6:10])
                        except ValueError:
                            pass
                            
                    score = 0
                    if extracted_issuer:
                        ext_iss_norm = norm_agency(extracted_issuer)
                        iss_db_norm = norm_agency(co_quan_ban_hanh)
                        if ext_iss_norm in iss_db_norm or iss_db_norm in ext_iss_norm:
                            score += 100
                    elif detected_locality:
                        # Fallback: match tên tỉnh/thành phố trực tiếp
                        iss_db_lower = (co_quan_ban_hanh or "").lower()
                        if detected_locality in iss_db_lower:
                            score += 150  # Tăng weight locality để thắng title overlap
                        elif len(rows) > 3:
                            # Khi collision cao + có locality rõ ràng → penalty cho docs không khớp
                            score -= 50
                    
                    # ── Title-Query Word Overlap ──
                    # Khi nhiều docs trùng số hiệu, dùng overlap nội dung title
                    # để phân biệt doc nào khớp nhất với câu hỏi
                    if title and len(rows) > 1:
                        title_words = set(w.lower() for w in re.findall(r'\w+', title) if len(w) > 2)
                        query_words = set(w.lower() for w in re.findall(r'\w+', query) if len(w) > 2)
                        overlap = len(title_words & query_words)
                        if overlap >= 3:
                            score += min(overlap * 5, 60)  # Max +60 từ title overlap
                            
                    if extracted_year and year_db == extracted_year:
                        score += 50
                        
                    if extracted_doc_type:
                        dt_db_lower = (loai_van_ban or "").lower()
                        if extracted_doc_type.lower() == dt_db_lower:
                            score += 20
                            
                    scored_docs.append((score, doc_id, ngay_ban_hanh))
                
                # Sort primarily by metadata match score, then chronologically (newest first)
                scored_docs.sort(key=lambda x: (x[0], parse_db_date(x[2])), reverse=True)
                
                # ── Smart filtering: when strong issuer/locality match exists, ──
                # ── only use docs from that match to avoid province collisions ──
                top_score = scored_docs[0][0] if scored_docs else 0
                if top_score >= 100 and (extracted_issuer or detected_locality):
                    # Strong issuer match: only take docs with matching score
                    filtered_docs = [(s, did, d) for s, did, d in scored_docs if s >= 100]
                    doc_ids_with_score = [(did, s) for s, did, d in filtered_docs][:3]
                    print(f"🎯 Issuer/locality filter: {len(scored_docs)} → {len(doc_ids_with_score)} docs (top_score={top_score})")
                else:
                    doc_ids_with_score = [(did, s) for s, did, d in scored_docs][:5]
                
                for doc_id, doc_score in doc_ids_with_score:
                    # Step 2: Retrieve chunks for the specific doc_id using fast primary key and index
                    if dieu_match:
                        dieu_num = dieu_match.group(1)
                        cursor.execute("""
                            SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                                   d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                                   d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                                   d.ngay_ban_hanh as document_ngay_ban_hanh
                            FROM document_chunks c
                            JOIN documents d ON c.doc_id = d.id
                            WHERE c.doc_id = ?
                            AND c.chunk_header LIKE ?
                            ORDER BY c.chunk_index
                            LIMIT 5
                        """, (doc_id, f"Điều {dieu_num}%"))
                    else:
                        cursor.execute("""
                            SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                                   d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                                   d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                                   d.ngay_ban_hanh as document_ngay_ban_hanh
                            FROM document_chunks c
                            JOIN documents d ON c.doc_id = d.id
                            WHERE c.doc_id = ?
                            AND c.chunk_type = 'dieu'
                            ORDER BY c.chunk_index
                            LIMIT 5
                        """, (doc_id,))
                    
                    for row in cursor.fetchall():
                        item = dict(row)
                        # Propagate doc-level locality score into chunk score
                        item["score"] = 1000.0 + doc_score  # Higher score for locality-matched docs
                        item["is_exact_match"] = True
                        exact_chunks.append(item)
            
            if exact_chunks:
                print(f"📌 Exact match '{so_hieu}': {len(exact_chunks)} chunks injected into pool")
        except Exception as e:
            print(f"⚠️ Exact match lookup error: {e}")
        finally:
            conn.close()
            
    # ── Step 0.1: TITLE MATCH BOOST ──
    # Nhận diện các tiêu đề văn bản/luật được nhắc bằng chữ (ví dụ: "Luật Hôn nhân gia đình")
    try:
        from app.utils.entity_extractor import extract_entities
        matched_doc_ids = extract_entities(query)
        if matched_doc_ids:
            conn = get_db_connection()
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(matched_doc_ids))
            
            if dieu_match:
                dieu_num = dieu_match.group(1)
                cursor.execute(f"""
                    SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                           d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                           d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                           d.ngay_ban_hanh as document_ngay_ban_hanh
                    FROM document_chunks c
                    JOIN documents d ON c.doc_id = d.id
                    WHERE c.doc_id IN ({placeholders})
                    AND c.chunk_header LIKE ?
                    ORDER BY c.chunk_index
                    LIMIT 5
                """, (*matched_doc_ids, f"Điều {dieu_num}%"))
            else:
                cursor.execute(f"""
                    SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                           d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                           d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                           d.ngay_ban_hanh as document_ngay_ban_hanh
                    FROM document_chunks c
                    JOIN documents d ON c.doc_id = d.id
                    WHERE c.doc_id IN ({placeholders})
                    AND c.chunk_index <= 2
                    ORDER BY c.chunk_index
                """, tuple(matched_doc_ids))
                
            injected_count = 0
            for row in cursor.fetchall():
                item = dict(row)
                item["score"] = 10.0
                if not any(ec["id"] == item["id"] for ec in exact_chunks):
                    exact_chunks.append(item)
                    injected_count += 1
            conn.close()
            if injected_count > 0:
                print(f"📌 Title/Num Entity match: {len(matched_doc_ids)} docs detected, injected {injected_count} chunks")
    except Exception as e:
        print(f"⚠️ Title match boost error: {e}")
    
    # ── Step 0.1.5: TITLE FTS5 MATCH BOOST ──
    # Exact phrase search trên title. Chỉ chạy khi KHÔNG CÓ exact match từ số hiệu.
    if not exact_chunks:
        query_words_count = len(query_norm_spaces.split())
        if query_norm_spaces and query_words_count < 15:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                phrase_clean = query_norm_spaces.replace('"', '').replace("'", "")
                # Loại bỏ prefix generic để FTS5 match chính xác hơn
                phrase_clean = re.sub(
                    r'^(theo quy định hiện hành,?\s*|pháp luật quy định như thế nào về\s*|quy định về\s*)',
                    '', phrase_clean, flags=re.IGNORECASE
                ).strip()
                if len(phrase_clean) > 8:
                    fts_query = f'title : "{phrase_clean}"'
                    cursor.execute("""
                        SELECT d.id
                        FROM documents_fts f
                        JOIN documents d ON f.rowid = d.id
                        WHERE documents_fts MATCH ?
                        LIMIT 5
                    """, (fts_query,))
                    
                    matched_doc_ids = [row[0] for row in cursor.fetchall()]
                    if matched_doc_ids:
                        placeholders = ",".join(["?"] * len(matched_doc_ids))
                        cursor.execute(f"""
                            SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                                   d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                                   d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                                   d.ngay_ban_hanh as document_ngay_ban_hanh
                            FROM document_chunks c
                            JOIN documents d ON c.doc_id = d.id
                            WHERE c.doc_id IN ({placeholders})
                            AND c.chunk_index <= 2
                            ORDER BY c.chunk_index
                        """, tuple(matched_doc_ids))
                        
                        title_fts_count = 0
                        for row in cursor.fetchall():
                            item = dict(row)
                            item["score"] = 600.0
                            item["is_title_fts_match"] = True
                            if not any(ec["id"] == item["id"] for ec in exact_chunks):
                                exact_chunks.append(item)
                                title_fts_count += 1
                        if title_fts_count:
                            print(f"📌 Title FTS match for '{phrase_clean[:50]}': injected {title_fts_count} chunks")
            except Exception as e:
                print(f"⚠️ Title FTS match boost error: {e}")
            finally:
                conn.close()

    # ── Step 0.2: FTS5 EXACT PHRASE BOOST for fragment queries ──
    # When query contains a quoted fragment or looks like a verbatim text paste,
    # use FTS5 phrase matching to find chunks with the exact text
    quoted_match = re.search(r'"(.{10,})"', query)  # Extract quoted fragment
    if not quoted_match:
        # Detect fragment-style queries (long, looks like pasted content)
        clean_q = re.sub(
            r'^(tìm giúp tôi|nội dung|quy định|cho tôi biết|điều luật nào|tìm giúp tôi điều luật có nội dung:?)[\s:"]*',
            '', query, flags=re.IGNORECASE
        ).strip().strip('"')
        if len(clean_q.split()) > 6:
            quoted_match = type('obj', (object,), {'group': lambda self, x: clean_q})()

    if quoted_match:
        phrase = quoted_match.group(1).strip()
        if len(phrase) > 8:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                fts_phrase = '"' + phrase.replace('"', '').replace("'", '') + '"'
                cursor.execute("""
                    SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header,
                           c.chunk_text, c.chunk_with_meta, c.token_estimate,
                           d.title as document_title, d.so_ky_hieu as document_so_ky_hieu,
                           d.loai_van_ban as document_loai_van_ban,
                           d.co_quan_ban_hanh as document_co_quan_ban_hanh,
                           d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                           d.ngay_ban_hanh as document_ngay_ban_hanh
                    FROM chunks_fts f
                    JOIN document_chunks c ON c.id = f.rowid
                    JOIN documents d ON c.doc_id = d.id
                    WHERE chunks_fts MATCH ?
                    LIMIT 100
                """, (fts_phrase,))

                fts_count = 0
                for row in cursor.fetchall():
                    item = dict(row)
                    base_score = 800.0
                    
                    boost_multiplier = 1.0
                    doc_type_db = (item.get("document_loai_van_ban") or "").lower()
                    issuer_db = (item.get("document_co_quan_ban_hanh") or "").lower()
                    date_db = item.get("document_ngay_ban_hanh") or ""
                    
                    year_db = None
                    if date_db and len(date_db) >= 10:
                        try:
                            year_db = int(date_db[6:10])
                        except ValueError:
                            pass
                            
                    if extracted_doc_type and extracted_doc_type.lower() == doc_type_db:
                        boost_multiplier *= 2.0
                        
                    if extracted_issuer:
                        def norm_agency(val):
                            if not val:
                                return ""
                            val = val.lower()
                            val = val.replace("ubnd", "ủy ban nhân dân")
                            val = val.replace("hđnd", "hội đồng nhân dân")
                            return val
                        ext_iss_norm = norm_agency(extracted_issuer)
                        issuer_db_norm = norm_agency(issuer_db)
                        if ext_iss_norm in issuer_db_norm or issuer_db_norm in ext_iss_norm:
                            boost_multiplier *= 2.0
                            
                    if extracted_year and year_db == extracted_year:
                        boost_multiplier *= 3.0
                        
                    item["score"] = base_score * boost_multiplier
                    item["is_fts_phrase_match"] = True
                    
                    if not any(ec["id"] == item["id"] for ec in exact_chunks):
                        exact_chunks.append(item)
                        fts_count += 1
                        
                # Sort exact_chunks descending by score
                exact_chunks.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                
                if fts_count:
                    print(f"📝 FTS5 phrase match '{phrase[:30]}...': {fts_count} chunks boosted")
            except Exception as e:
                print(f"⚠️ FTS5 phrase boost error: {e}")
            finally:
                conn.close()

    # ── Step 1: Fetch top candidates from smart hybrid search ──
    search_res = smart_search_laws(
        q=query,
        loai_van_ban=extracted_doc_type,
        co_quan_ban_hanh=extracted_issuer,
        status=None,
        linh_vuc=None,
        limit=40,
        offset=0,
        nam_ban_hanh=extracted_year,
        use_soft_boosting=True,
        _key=None,
        query_vector=query_vector
    )
    results = search_res.get("results") or []
    
    # Merge exact match chunks into results (deduplicate by doc_id + chunk_index)
    if exact_chunks:
        exact_keys = {(ec.get("doc_id"), ec.get("chunk_index", 0)) for ec in exact_chunks}
        results = [item for item in results if (item.get("doc_id"), item.get("chunk_index", 0)) not in exact_keys]
        results = exact_chunks + results
    
    # 2. Apply domain intent scoring (soft penalty, NOT hard filter)
    # P2 Fix: Instead of removing non-matching chunks, we penalize their score.
    if domain_filter:
        for item in results:
            title = (item.get("document_title") or "").lower()
            so_ky_hieu = (item.get("document_so_ky_hieu") or "").lower()
            linh_vuc = (item.get("linh_vuc") or "").lower()
            
            match = False
            for term in domain_filter:
                term_lower = term.lower()
                if term_lower in title or term_lower in so_ky_hieu or term_lower in linh_vuc:
                    match = True
                    break
            
            if match:
                item["score"] = (item.get("score") or 0.0) * 1.2
            else:
                item["score"] = (item.get("score") or 0.0) * 0.6

    # 2.1. Apply soft metadata boosting (Year, Doc Type, Issuer) to prevent WRONG_DOC
    for item in results:
        doc_type_db = (item.get("document_loai_van_ban") or "").lower()
        issuer_db = (item.get("document_co_quan_ban_hanh") or "").lower()
        date_db = item.get("document_ngay_ban_hanh") or ""
        
        # Parse year from date_db (dd/mm/yyyy)
        year_db = None
        if date_db and len(date_db) >= 10:
            try:
                year_db = int(date_db[6:10])
            except ValueError:
                pass
                
        boost_multiplier = 1.0
        
        if extracted_doc_type and extracted_doc_type.lower() == doc_type_db:
            boost_multiplier *= 2.0
            
        if extracted_issuer:
            def norm_agency(val):
                if not val:
                    return ""
                val = val.lower()
                val = val.replace("ubnd", "ủy ban nhân dân")
                val = val.replace("hđnd", "hội đồng nhân dân")
                return val
            ext_iss_norm = norm_agency(extracted_issuer)
            issuer_db_norm = norm_agency(issuer_db)
            if ext_iss_norm in issuer_db_norm or issuer_db_norm in ext_iss_norm:
                boost_multiplier *= 2.0
                
        if extracted_year and year_db == extracted_year:
            boost_multiplier *= 3.0
            
        # ── Lex Hierarchy & Conflict Resolution Scoring (Lex Superior & Lex Posterior) ──
        hierarchy_weight = {
            "hiến pháp": 2.0, "bộ luật": 1.8, "luật": 1.7, "nghị quyết": 1.5,
            "pháp lệnh": 1.4, "nghị định": 1.3, "quyết định": 1.2, "thông tư": 1.1
        }
        for dt_key, weight in hierarchy_weight.items():
            if dt_key in doc_type_db:
                boost_multiplier *= weight
                break

        status_db = (item.get("document_tinh_trang_hieu_luc") or "").lower()
        if "còn hiệu lực" in status_db:
            boost_multiplier *= 1.3
        elif "hết hiệu lực" in status_db:
            boost_multiplier *= 0.5

        if year_db:
            if year_db >= 2024:
                boost_multiplier *= 1.25
            elif year_db >= 2020:
                boost_multiplier *= 1.15
            
        item["score"] = (item.get("score") or 0.0) * boost_multiplier
                
    # 2.2. Boilerplate Penalty (Phạt điểm các điều khoản thủ tục chung)
    try:
        boilerplate_patterns = [
            r"quyết định này có hiệu lực",
            r"thông tư này có hiệu lực",
            r"nghị định này có hiệu lực",
            r"luật này có hiệu lực",
            r"có hiệu lực thi hành kể từ",
            r"chịu trách nhiệm thi hành quyết định",
            r"chịu trách nhiệm thi hành thông tư",
            r"chịu trách nhiệm thi hành nghị định",
            r"chịu trách nhiệm thi hành luật",
            r"ban hành kèm theo quyết định này",
            r"ban hành kèm theo thông tư này",
            r"ban hành kèm theo nghị định này",
        ]
        bp_regexes = [re.compile(p, re.IGNORECASE) for p in boilerplate_patterns]
        
        query_lower = query.lower()
        has_hiệu_lực_intent = any(k in query_lower for k in ["hiệu lực", "ngày ký", "ngày có hiệu lực", "áp dụng từ"])
        has_thi_hành_intent = any(k in query_lower for k in ["thi hành", "trách nhiệm thi hành", "chịu trách nhiệm"])
        has_ban_hành_intent = any(k in query_lower for k in ["ban hành kèm theo", "kèm theo quyết định"])
        has_phạm_vi_intent = "phạm vi điều chỉnh" in query_lower or "phạm vi áp dụng" in query_lower
        
        for item in results:
            text = (item.get("chunk_text") or "").lower()
            header = (item.get("chunk_header") or "").lower()
            
            is_boilerplate = False
            if not has_hiệu_lực_intent:
                for rx in bp_regexes[:5]:
                    if rx.search(text):
                        is_boilerplate = True
                        break
            if not is_boilerplate and not has_thi_hành_intent:
                for rx in bp_regexes[5:9]:
                    if rx.search(text):
                        is_boilerplate = True
                        break
            if not is_boilerplate and not has_ban_hành_intent:
                for rx in bp_regexes[9:]:
                    if rx.search(text):
                        is_boilerplate = True
                        break
            if not is_boilerplate and not has_phạm_vi_intent:
                if "phạm vi điều chỉnh" in text and ("điều 1" in header or "điều 1" in text[:50]):
                    is_boilerplate = True
                    
            if is_boilerplate:
                base_score = item.get("score") or 0.0
                if base_score < 10.0:  # Không phạt các chunk được inject trực tiếp do khớp đích danh
                    item["score"] = base_score * 0.4
    except Exception as e:
        print(f"⚠️ Boilerplate penalty error: {e}")
    
    # 2.3. Text Fragment N-gram Overlap Scoring Boost
    # When user copies a text fragment and asks "which doc/article is this?",
    # boost chunks that contain a significant portion of the query text verbatim
    query_clean_accent = strip_accents_and_lowercase(query)
    query_words = [w for w in re.sub(r'[^\w\s]', ' ', query_clean_accent).split() if len(w) > 1]
    if len(query_words) > 8:  # Lowered threshold to catch shorter fragments
        try:
            for item in results:
                chunk_text_clean = strip_accents_and_lowercase(item.get("chunk_text") or "")
                if not chunk_text_clean:
                    continue

                # Sliding 3-gram overlap scoring (more granular than 5-gram)
                ngram_size = 3
                ngram_hits = 0
                for start in range(len(query_words) - ngram_size + 1):
                    ngram = " ".join(query_words[start:start + ngram_size])
                    if ngram in chunk_text_clean:
                        ngram_hits += 1
                total_ngrams = max(len(query_words) - ngram_size + 1, 1)
                match_ratio = ngram_hits / total_ngrams

                if match_ratio > 0.3:  # Lower threshold for partial matches
                    item["score"] = (item.get("score") or 0.0) + 800.0 * match_ratio
                    item["is_text_fragment_match"] = True
        except Exception as e:
            print(f"⚠️ Text fragment matching error: {e}")
    
    # All results proceed (no hard filter)
    filtered_results = results


    # Deduplicate documents for Graph expansion seed list
    initial_candidates = []
    seen_docs = set()
    for item in filtered_results:
        doc_id = item["doc_id"]
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            initial_candidates.append({
                "doc_id": doc_id,
                "score": item.get("score") or 0.0
            })
            
    # 3. Perform 1-hop Graph Expansion (HippoRAG style & LightGraph Store)
    try:
        from app.utils.light_graph_manager import LightGraphManager
        seed_ids = [c["doc_id"] for c in initial_candidates[:5]]
        connected_ids = LightGraphManager.query_graph_connections(seed_ids, max_depth=1)
        for cid in connected_ids:
            if cid not in seen_docs:
                seen_docs.add(cid)
                initial_candidates.append({
                    "doc_id": cid,
                    "score": 0.5
                })
    except Exception as e:
        print(f"⚠️ LightGraphManager traversal warning: {e}")
        
    expanded_docs = graph_expand_results(initial_candidates, query=query, hops=1, max_nodes=20)
    expanded_doc_ids = [doc["id"] for doc in expanded_docs]
    
    # Build candidate chunks list by pulling chunks belonging to the expanded docs
    chunk_candidates = []
    for item in filtered_results:
        if item["doc_id"] in expanded_doc_ids:
            # Combine the base chunk score with the Graph PPR-lite score
            doc_score = next((doc["score"] for doc in expanded_docs if doc["id"] == item["doc_id"]), 0.0)
            if item.get("is_exact_match"):
                # Preserve exact match score (already includes locality/issuer scoring)
                item["score"] = doc_score + (item.get("score") or 0.0)
            else:
                item["score"] = doc_score + (item.get("score") or 0.0) * 0.1
            chunk_candidates.append(item)
            
    # If the Graph expanded new documents that don't have chunks in our search results pool,
    # pull their introductory (first) chunk from the database
    existing_doc_ids = {c["doc_id"] for c in chunk_candidates}
    missing_doc_ids = [did for did in expanded_doc_ids if did not in existing_doc_ids]
    
    if missing_doc_ids:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(missing_doc_ids))
        try:
            cursor.execute(f"""
                SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.chunk_with_meta, c.token_estimate,
                       d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                       d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                       d.ngay_ban_hanh as document_ngay_ban_hanh
                FROM document_chunks c
                JOIN documents d ON c.doc_id = d.id
                WHERE c.doc_id IN ({placeholders}) AND c.chunk_index = 0
            """, missing_doc_ids)
            for row in cursor.fetchall():
                item = dict(row)
                doc_score = next((doc["score"] for doc in expanded_docs if doc["id"] == item["doc_id"]), 0.0)
                item["score"] = doc_score
                chunk_candidates.append(item)
        except Exception as e:
            print(f"⚠️ Error pulling missing graph chunk: {e}")
        finally:
            conn.close()
            
    # Re-sort candidates based on updated score and chronological date (newest first)
    def candidate_sort_key(x):
        date_str = x.get("document_ngay_ban_hanh") or x.get("ngay_ban_hanh") or ""
        return (x.get("score", 0.0), parse_db_date(date_str))
    
    chunk_candidates = sorted(chunk_candidates, key=candidate_sort_key, reverse=True)
    
    # 4. Perform Reranking (Cohere API or local Vietnamese Cross-Encoder)
    final_chunks = []
    
    # FPT Cloud Reranker API calling helper (using bge-reranker-v2-m3)
    async def fpt_rerank_vietnamese(q: str, candidates: list, n: int) -> list:
        from app.config import FPT_CLOUD_API_KEY
        if not FPT_CLOUD_API_KEY:
            print("⚠️ FPT_CLOUD_API_KEY not configured. Bypassing FPT Reranker.")
            return []
        
        url = "https://mkp-api.fptcloud.com/v1/rerank"
        headers = {
            "Authorization": f"Bearer {FPT_CLOUD_API_KEY}",
            "Content-Type": "application/json"
        }
        
        passages = []
        candidates_slice = candidates[:20]
        for c in candidates_slice:
            text = c.get("chunk_with_meta") or c.get("chunk_text") or ""
            doc_title = c.get("document_title") or ""
            doc_ky_hieu = c.get("document_so_ky_hieu") or ""
            if doc_title or doc_ky_hieu:
                text = f"[{doc_ky_hieu}] {doc_title}: {text}"
            passages.append(text)
            
        payload = {
            "model": "bge-reranker-v2-m3",
            "query": q,
            "documents": passages,
            "top_n": n
        }
        
        sem = get_fpt_rerank_semaphore()
        async with sem:
            for attempt in range(3):
                try:
                    import httpx
                    import asyncio
                    async with httpx.AsyncClient() as client:
                        response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                        if response.status_code == 200:
                            res_data = response.json()
                            results = res_data.get("results") or []
                            
                            reranked_chunks = []
                            for item in results:
                                idx = item["index"]
                                score = item["relevance_score"]
                                original_chunk = candidates_slice[idx].copy()
                                original_score = original_chunk.get("score", 0.0)
                                # Blend: reranker semantic score + original metadata/locality score
                                # This preserves province/issuer disambiguation while benefiting from reranking
                                if original_chunk.get("is_exact_match"):
                                    # Exact match: keep high base + add reranker as tiebreaker
                                    original_chunk["score"] = original_score + float(score) * 10.0
                                else:
                                    # Non-exact: reranker-dominant but preserve some metadata signal
                                    original_chunk["score"] = float(score) * 100.0 + original_score * 0.01
                                reranked_chunks.append(original_chunk)
                                
                            print(f"⚡ Reranked {len(candidates_slice)} chunks using FPT Cloud Reranker API ({len(reranked_chunks[:n])} returned)")
                            return reranked_chunks[:n]
                        else:
                            print(f"⚠️ FPT Reranker API returned error: {response.status_code} | {response.text}")
                            return []
                except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                    if attempt == 0:
                        print(f"⚠️ FPT Reranker API ConnectTimeout/Error. Retrying attempt {attempt+2}...")
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        print(f"⚠️ FPT Reranker API call failed after retries: {type(e).__name__}: {e}")
                        return []
                except Exception as e:
                    import traceback
                    print(f"⚠️ FPT Reranker API call failed: {type(e).__name__}: {e}")
                    traceback.print_exc()
                    return []

    # Uses AITeamVN/Vietnamese_Reranker instead of FlashRank TinyBERT
    def local_rerank_vietnamese(q: str, candidates: list, n: int) -> list:
        try:
            import torch
            from app.routers.laws import get_vietnamese_reranker
            model, tokenizer = get_vietnamese_reranker()
            
            if model is not None and tokenizer is not None:
                # Score each candidate using Cross-Encoder
                pairs = []
                for c in candidates[:20]:
                    text = c.get("chunk_with_meta") or c.get("chunk_text") or ""
                    # Enrich with document context for better disambiguation
                    doc_title = c.get("document_title") or ""
                    doc_ky_hieu = c.get("document_so_ky_hieu") or ""
                    if doc_title or doc_ky_hieu:
                        text = f"[{doc_ky_hieu}] {doc_title}: {text}"
                    pairs.append([q, text])
                
                device = next(model.parameters()).device
                with torch.no_grad():
                    inputs = tokenizer(
                        pairs, padding=True, truncation=True, 
                        max_length=512, return_tensors="pt"
                    ).to(device)
                    scores = model(**inputs).logits.squeeze(-1)
                    if scores.dim() == 0:
                        scores = scores.unsqueeze(0)
                    scores = scores.cpu().tolist()
                
                # Pair scores with candidates, boosting exact matches
                scored = []
                for score, chunk in zip(scores, candidates[:len(scores)]):
                    s = float(score)
                    if chunk.get("is_exact_match"):
                        s += 1000.0
                    scored.append((s, chunk))
                scored.sort(key=lambda x: x[0], reverse=True)
                
                result = []
                for score, chunk in scored[:n]:
                    c = chunk.copy()
                    c["score"] = float(score)
                    result.append(c)
                
                print(f"⚡ Reranked {len(candidates[:20])} chunks using Vietnamese Cross-Encoder → top {n}")
                return result
            else:
                # Vietnamese reranker not available, fall back to FlashRank
                print("⚠️ Vietnamese Reranker not loaded. Falling back to FlashRank.")
                from app.utils.reranker_manager import get_reranker
                reranker = get_reranker()
                raw_reranked = reranker.rerank(q, candidates[:20], top_n=n)
                for item in raw_reranked:
                    if item.get("is_exact_match"):
                        item["score"] = (item.get("score") or 0.0) + 1000.0
                return sorted(raw_reranked, key=lambda x: x.get("score", 0.0), reverse=True)[:n]
                
        except Exception as err:
            print(f"⚠️ Vietnamese reranker failed: {err}. Falling back to FlashRank.")
            try:
                from app.utils.reranker_manager import get_reranker
                reranker = get_reranker()
                raw_reranked = reranker.rerank(q, candidates[:20], top_n=n)
                for item in raw_reranked:
                    if item.get("is_exact_match"):
                        item["score"] = (item.get("score") or 0.0) + 1000.0
                return sorted(raw_reranked, key=lambda x: x.get("score", 0.0), reverse=True)[:n]
            except Exception as err2:
                print(f"⚠️ FlashRank also failed: {err2}. Using raw sorted order.")
                raw_candidates = candidates[:n]
                for item in raw_candidates:
                    if item.get("is_exact_match"):
                        item["score"] = (item.get("score") or 0.0) + 1000.0
                return sorted(raw_candidates, key=lambda x: x.get("score", 0.0), reverse=True)

    # Determine which reranker to use
    # DISABLE_RERANKER=1 tắt hoàn toàn mọi reranker (FPT + local)
    disable_reranker = os.environ.get("DISABLE_RERANKER") == "1"
    use_fpt_reranker = (
        not disable_reranker
        and os.environ.get("USE_FPT_RERANKER", "true").lower() == "true"
        and os.environ.get("ACTIVE_LLM_PROVIDER") == "fpt"
    )
    use_local_reranker = (
        not disable_reranker
        and os.environ.get("USE_LOCAL_RERANKER", "false").lower() == "true"
    )
    
    if chunk_candidates:
        if use_fpt_reranker:
            final_chunks = await fpt_rerank_vietnamese(query, chunk_candidates, top_k)
            if not final_chunks:
                # FPT failed → luôn thử local Cross-Encoder trước khi dùng raw scores
                print("⚡ FPT Reranker failed → Falling back to local Vietnamese Cross-Encoder...")
                final_chunks = local_rerank_vietnamese(query, chunk_candidates, top_k)
                if not final_chunks:
                    print("⚡ Local Cross-Encoder also unavailable. Using raw candidate scores.")
                    final_chunks = chunk_candidates[:top_k]
                    for item in final_chunks:
                        if item.get("is_exact_match"):
                            item["score"] = (item.get("score") or 0.0) + 1000.0
        elif use_local_reranker:
            final_chunks = local_rerank_vietnamese(query, chunk_candidates, top_k)
        elif disable_reranker:
            print("⚡ Reranker disabled (DISABLE_RERANKER=1). Using raw candidate scores.")
            final_chunks = chunk_candidates[:top_k]
            for item in final_chunks:
                if item.get("is_exact_match"):
                    item["score"] = (item.get("score") or 0.0) + 1000.0
        else:
            print("⚡ No reranker configured. Using raw candidate scores.")
            final_chunks = chunk_candidates[:top_k]
            for item in final_chunks:
                if item.get("is_exact_match"):
                    item["score"] = (item.get("score") or 0.0) + 1000.0
    else:
        final_chunks = []
            
    # Force exact matches to the top of final_chunks (with chronological date tie-breaker)
    if final_chunks:
        def final_sort_key(x):
            date_str = x.get("document_ngay_ban_hanh") or x.get("ngay_ban_hanh") or ""
            return (1 if x.get("is_exact_match") else 0, x.get("score", 0.0), parse_db_date(date_str))
        final_chunks = sorted(final_chunks, key=final_sort_key, reverse=True)
        
    # 5. Format results with Citation anchors [Cx]
    formatted_parts = []
    citation_map = {}
    
    for idx, item in enumerate(final_chunks):
        cid_label = f"C{idx+1}"
        citation_map[cid_label] = {
            "id": item["doc_id"],
            "title": item["document_title"],
            "so_ky_hieu": item["document_so_ky_hieu"],
            "loai_van_ban": item["document_loai_van_ban"],
            "tinh_trang_hieu_luc": item["document_tinh_trang_hieu_luc"]
        }
        
        header = item.get("chunk_header") or f"Điều khoản {item.get('chunk_index', 0)}"
        doc_title = item.get("document_title") or "Văn bản"
        so_ky_hieu = item.get("document_so_ky_hieu") or "N/A"
        
        part = (
            f"[{cid_label}] [{doc_title} - Số hiệu: {so_ky_hieu} - {header}]\n"
            f"{item['chunk_text']}"
        )
        formatted_parts.append(part)
        
    formatted_chunks = "\n\n====================\n\n".join(formatted_parts)
    return formatted_chunks, citation_map

def apply_lex_conflict_resolution(chunks: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
    """
    Áp dụng thứ bậc Lex Superior (Hiến pháp -> Luật -> Nghị định -> Thông tư)
    và Lex Posterior (Ưu tiên luật mới ban hành hơn) theo Điều 156 Luật Ban hành VBQPPL.
    """
    hierarchy_weight = {
        "hiến pháp": 2.0, "bộ luật": 1.8, "luật": 1.7, "nghị quyết": 1.5,
        "pháp lệnh": 1.4, "nghị định": 1.3, "quyết định": 1.2, "thông tư": 1.1
    }
    
    resolved_chunks = []
    for item in chunks:
        c = dict(item)
        score = c.get("score") or 1.0
        doc_type = (c.get("document_loai_van_ban") or c.get("loai_van_ban") or "").lower()
        
        weight = 1.0
        for dt_key, w in hierarchy_weight.items():
            if dt_key in doc_type:
                weight = w
                break
                
        status = (c.get("document_tinh_trang_hieu_luc") or c.get("tinh_trang_hieu_luc") or "").lower()
        if "còn hiệu lực" in status:
            weight *= 1.2
        elif "hết hiệu lực" in status:
            weight *= 0.3
            
        c["score"] = score * weight
        resolved_chunks.append(c)
        
    resolved_chunks.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return resolved_chunks
