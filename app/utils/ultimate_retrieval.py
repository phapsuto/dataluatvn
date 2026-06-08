import os
import requests
from typing import List, Dict, Any, Tuple
from app.routers.laws import smart_search_laws
from app.utils.graph_retrieval import graph_expand_results
from app.database import get_db_connection

# Load Cohere API Key from environment if available
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

def ultimate_retrieve(
    query: str, 
    domain_filter: List[str] = None, 
    top_k: int = 5
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Orchestrates the entire retrieval pipeline:
    1. Base Hybrid Search: Calls smart_search_laws for raw FTS5 + FAISS Vector candidates.
    2. Intent Filtering: Filters candidates using keywords from the domain intent router.
    3. Graph Expansion: Traverses the relationships graph to pull modified/replacing laws.
    4. Reranking: Reranks the top chunks using Cohere Multilingual Rerank (or local fallback).
    5. Anchor Mapping: Formats output text with [C1], [C2] anchors and returns the citation map.
    """
    # 1. Fetch top candidates from smart hybrid search
    # We fetch a larger pool (40) to allow for domain filtering and graph expansion
    # We pass all parameters explicitly to prevent FastAPI Query objects from being used as default values
    search_res = smart_search_laws(
        q=query,
        loai_van_ban=None,
        co_quan_ban_hanh=None,
        status=None,
        linh_vuc=None,
        limit=40,
        offset=0,
        _key=None
    )
    results = search_res.get("results") or []
    
    # 2. Filter by domain intent keywords if provided
    filtered_results = []
    if domain_filter:
        for item in results:
            title = (item.get("document_title") or "").lower()
            so_ky_hieu = (item.get("document_so_ky_hieu") or "").lower()
            
            # Keep document if title or symbol matches any of the domain filter keywords
            match = False
            for term in domain_filter:
                if term.lower() in title or term.lower() in so_ky_hieu:
                    match = True
                    break
            if match:
                filtered_results.append(item)
                
        # If filtering is too aggressive and yields empty list, fallback to original list
        if not filtered_results:
            filtered_results = results
    else:
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
            
    # 3. Perform 1-hop Graph Expansion (HippoRAG style)
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
                SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.token_estimate,
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
    
    # 4. Perform Cohere Rerank if API Key is available
    final_chunks = []
    if COHERE_API_KEY and chunk_candidates:
        try:
            # Call Cohere Rerank API
            url = "https://api.cohere.ai/v1/rerank"
            headers = {
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json"
            }
            documents_to_rerank = [c["chunk_text"] for c in chunk_candidates[:20]]
            payload = {
                "model": "rerank-multilingual-v3.0",
                "query": query,
                "documents": documents_to_rerank,
                "top_n": min(top_k, len(documents_to_rerank))
            }
            response = requests.post(url, json=payload, headers=headers, timeout=5.0)
            if response.status_code == 200:
                rerank_results = response.json().get("results") or []
                for r in rerank_results:
                    idx = r["index"]
                    item = chunk_candidates[idx]
                    item["score"] = r["relevance_score"]
                    final_chunks.append(item)
            else:
                print(f"⚠️ Cohere API error: {response.text}. Using local ranking fallback.")
                final_chunks = chunk_candidates[:top_k]
        except Exception as e:
            print(f"⚠️ Cohere Rerank failed: {e}. Using local ranking fallback.")
            final_chunks = chunk_candidates[:top_k]
    else:
        # Fallback to local scored list (already sorted)
        final_chunks = chunk_candidates[:top_k]
        
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
