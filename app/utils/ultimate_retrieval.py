import os
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from app.routers.laws import smart_search_laws
from app.utils.graph_retrieval import graph_expand_results
from app.database import get_db_connection



def ultimate_retrieve(
    query: str, 
    domain_filter: List[str] = None, 
    top_k: int = 5,
    extracted_year: Optional[int] = None,
    extracted_doc_type: Optional[str] = None,
    extracted_issuer: Optional[str] = None
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Pipeline retrieval: Exact Match → Smart Search (FTS5 + FAISS + RRF) → Graph Expansion → Rerank.
    Returns formatted chunks string and citation_map dict.
    """
    # ── Step 0: EXACT MATCH BOOST ──
    # Nếu query chứa số hiệu VB cụ thể → fetch trực tiếp từ DB và inject vào pool
    exact_chunks = []
    query_norm_spaces = re.sub(r'\s*/\s*', '/', query)
    so_ky_hieu_match = re.search(
        r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|\b\d+-[A-Za-zĐđÀ-ỹ]{2,}\b)',
        query_norm_spaces
    )
    dieu_match = re.search(r'[Đđ]iều\s+(\d+)', query)
    
    if so_ky_hieu_match:
        so_hieu = so_ky_hieu_match.group(0).strip()
        so_hieu_clean = so_hieu.replace(' ', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Step 1: Find the doc_id from documents table using indexed search
            cursor.execute("SELECT id FROM documents WHERE so_ky_hieu = ?", (so_hieu,))
            row = cursor.fetchone()
            if not row:
                # Fallback to whitespace-stripped search (covers documents with messy symbol spaces)
                cursor.execute("SELECT id FROM documents WHERE REPLACE(so_ky_hieu, ' ', '') = ?", (so_hieu_clean,))
                row = cursor.fetchone()
                
            if row:
                doc_id = row[0]
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
                    item["score"] = 1000.0  # High base score
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
    # If the search query is a meaningful phrase (< 10 words),
    # boost documents whose titles contain the phrase using documents_fts index.
    # Exclude very generic stop phrases to prevent broad matches.
    stop_phrases = ["phạm vi điều chỉnh", "đối tượng áp dụng", "hiệu lực thi hành", "quyết định này có hiệu lực"]
    query_words_count = len(query_norm_spaces.split())
    if query_norm_spaces and query_words_count < 10 and not any(sp in query_norm_spaces.lower() for sp in stop_phrases):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            phrase_clean = query_norm_spaces.replace('"', '').replace("'", "")
            # FTS5 search exact phrase in title column
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
                    item["score"] = 600.0  # High score boost for exact title match
                    item["is_title_fts_match"] = True
                    if not any(ec["id"] == item["id"] for ec in exact_chunks):
                        exact_chunks.append(item)
                        title_fts_count += 1
                if title_fts_count:
                    print(f"📌 Title FTS match for '{phrase_clean}': injected {title_fts_count} chunks")
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
                    LIMIT 10
                """, (fts_phrase,))

                fts_count = 0
                for row in cursor.fetchall():
                    item = dict(row)
                    item["score"] = 800.0
                    item["is_fts_phrase_match"] = True
                    if not any(ec["id"] == item["id"] for ec in exact_chunks):
                        exact_chunks.append(item)
                        fts_count += 1
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
        _key=None
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
            except:
                pass
                
        boost_multiplier = 1.0
        
        if extracted_doc_type and extracted_doc_type.lower() == doc_type_db:
            boost_multiplier *= 2.0
            
        if extracted_issuer:
            ext_iss_lower = extracted_issuer.lower()
            if ext_iss_lower in issuer_db or issuer_db in ext_iss_lower:
                boost_multiplier *= 2.0
                
        if extracted_year and year_db == extracted_year:
            boost_multiplier *= 3.0
            
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
    query_words = [w.lower() for w in re.sub(r'[^\w\s]', ' ', query).split() if len(w) > 1]
    if len(query_words) > 8:  # Lowered threshold to catch shorter fragments
        try:
            for item in results:
                chunk_text_lower = (item.get("chunk_text") or "").lower()
                if not chunk_text_lower:
                    continue

                # Sliding 3-gram overlap scoring (more granular than 5-gram)
                ngram_size = 3
                ngram_hits = 0
                for start in range(len(query_words) - ngram_size + 1):
                    ngram = " ".join(query_words[start:start + ngram_size])
                    if ngram in chunk_text_lower:
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
            
    # Re-sort candidates based on updated score
    chunk_candidates = sorted(chunk_candidates, key=lambda x: x["score"], reverse=True)
    
    # 4. Perform Reranking (Cohere API or local Vietnamese Cross-Encoder)
    final_chunks = []
    
    # Helper for local Vietnamese Cross-Encoder reranking (P2 Fix #9)
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

    # Use local Vietnamese Cross-Encoder reranker
    if chunk_candidates:
        final_chunks = local_rerank_vietnamese(query, chunk_candidates, top_k)
    else:
        final_chunks = []
            
    # Force exact matches to the top of final_chunks (stable sort)
    if final_chunks:
        final_chunks = sorted(final_chunks, key=lambda x: 1 if x.get("is_exact_match") else 0, reverse=True)
        
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
