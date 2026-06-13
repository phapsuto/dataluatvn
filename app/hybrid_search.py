"""
Hybrid Search Engine: BM25Okapi + FTS5 với Reciprocal Rank Fusion (RRF)

Kiến trúc:
1. BM25Okapi (rank_bm25): Scoring chính xác hơn FTS5, xử lý IDF tốt hơn
2. FTS5 content_fts: Tìm kiếm nhanh trên SQLite
3. RRF: Kết hợp ranking từ cả 2 nguồn → kết quả tối ưu

Lấy cảm hứng từ:
- tnt305/vietnamese-legal-retrieval (SOICT 2024)
- NamSyntax/vietnamese-rag-system
"""

import sqlite3
import re
import time
import sys
import os
import pickle
from typing import List, Dict, Tuple, Optional
from html.parser import HTMLParser

# Lazy imports
_bm25 = None
_word_tokenize = None

def _get_bm25():
    global _bm25
    if _bm25 is None:
        from rank_bm25 import BM25Okapi
        _bm25 = BM25Okapi
    return _bm25

def _get_tokenizer():
    global _word_tokenize
    if _word_tokenize is None:
        try:
            from underthesea import word_tokenize
            _word_tokenize = word_tokenize
        except ImportError:
            # Fallback: simple split
            _word_tokenize = lambda text: text.split()
    return _word_tokenize

# Vietnamese stopwords
STOPWORDS = {
    "của", "và", "với", "trong", "trên", "dưới", "ngoài", "giữa", "bên", "về",
    "cho", "đến", "từ", "tại", "theo", "bằng", "qua", "vào", "hay", "hoặc",
    "nhưng", "mà", "rằng", "nếu", "khi", "vì", "do", "bởi", "để",
    "đã", "đang", "sẽ", "sắp", "vẫn", "còn", "rất", "lắm", "quá", "hơn",
    "nhất", "không", "chưa", "chẳng", "nên", "cần", "phải", "được", "bị",
    "có", "là", "thì", "cũng", "lại", "rồi", "mới", "cứ", "đều",
    "tôi", "tui", "mình", "ta", "chúng", "các", "những", "một", "này", "đó",
    "nào", "gì", "ai", "đâu", "sao", "bao", "mấy", "thế", "như", "vậy",
    # LƯU Ý: "điều" và "khoản" KHÔNG phải stopwords vì là identifier pháp lý cốt lõi
    "việc", "cái", "con", "người",
}

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'svg', 'iframe', 'img'):
            self._skip = True
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg', 'iframe', 'img'):
            self._skip = False
        if tag in ('p', 'br', 'div', 'tr', 'li', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._text.append(' ')
    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)
    def get_text(self):
        return ' '.join(self._text)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        e = HTMLTextExtractor()
        e.feed(html)
        text = e.get_text()
    except:
        text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def tokenize_vi(text: str) -> List[str]:
    """Tokenize văn bản tiếng Việt: lowercase + remove stopwords."""
    if not text:
        return []
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    words = text.split()
    return [w for w in words if len(w) > 1 and w not in STOPWORDS]


class HybridSearchEngine:
    """
    Engine tìm kiếm lai: BM25Okapi + FTS5 với RRF.
    
    Sử dụng:
        engine = HybridSearchEngine(main_db, content_db)
        engine.build_index()  # Chỉ cần chạy 1 lần
        results = engine.search("luật đất đai", top_k=10)
    """
    
    def __init__(self, main_db_path: str, content_db_path: str, cache_path: str = None):
        self.main_db_path = main_db_path
        self.content_db_path = content_db_path
        self.cache_path = cache_path or os.path.join(os.path.dirname(main_db_path), "bm25_index.pkl")
        
        self.bm25 = None
        self.doc_ids = []  # Mapping: index → doc_id
        self.doc_meta = {}  # doc_id → {title, so_ky_hieu, ...}
        self._ready = False
    
    def build_index(self, max_content_chars: int = 8000):
        """Xây dựng BM25 index từ content_store.db."""
        
        # Kiểm tra cache
        if os.path.exists(self.cache_path):
            try:
                return self._load_cache()
            except Exception as e:
                print(f"   ⚠️ Cache lỗi: {e}, rebuild...")
        
        print("🏗️  Đang xây dựng BM25 index...")
        start = time.time()
        
        # Load metadata
        main_conn = sqlite3.connect(self.main_db_path)
        main_cursor = main_conn.cursor()
        main_cursor.execute("SELECT id, title, so_ky_hieu, loai_van_ban, tinh_trang_hieu_luc, co_quan_ban_hanh, ngay_ban_hanh FROM documents")
        
        for row in main_cursor.fetchall():
            self.doc_meta[row[0]] = {
                "title": row[1] or "",
                "so_ky_hieu": row[2] or "",
                "loai_van_ban": row[3] or "",
                "tinh_trang_hieu_luc": row[4] or "",
                "co_quan_ban_hanh": row[5] or "",
                "ngay_ban_hanh": row[6] or "",
            }
        main_conn.close()
        
        # Load content & tokenize
        content_conn = sqlite3.connect(self.content_db_path)
        content_cursor = content_conn.cursor()
        content_cursor.execute("SELECT doc_id, content_html FROM document_content ORDER BY doc_id")
        
        corpus = []
        processed = 0
        
        for row in content_cursor:
            doc_id, content_html = row
            
            meta = self.doc_meta.get(doc_id, {})
            title = meta.get("title", "")
            so_ky_hieu = meta.get("so_ky_hieu", "")
            
            # Kết hợp title + content (title trọng số cao hơn bằng lặp lại)
            content_text = html_to_text(content_html)[:max_content_chars] if content_html else ""
            full_text = f"{title} {title} {title} {so_ky_hieu} {content_text}"
            
            tokens = tokenize_vi(full_text)
            if tokens:
                corpus.append(tokens)
                self.doc_ids.append(doc_id)
            
            processed += 1
            if processed % 10000 == 0:
                sys.stdout.write(f"\r   Tokenized: {processed} documents...")
                sys.stdout.flush()
        
        content_conn.close()
        
        # Thêm documents không có content (chỉ title)
        content_doc_ids = set(self.doc_ids)
        for doc_id, meta in self.doc_meta.items():
            if doc_id not in content_doc_ids:
                title = meta.get("title", "")
                so_ky_hieu = meta.get("so_ky_hieu", "")
                tokens = tokenize_vi(f"{title} {title} {title} {so_ky_hieu}")
                if tokens:
                    corpus.append(tokens)
                    self.doc_ids.append(doc_id)
        
        # Build BM25
        print(f"\r   Tokenized: {len(corpus)} documents. Building BM25Okapi...")
        BM25Okapi = _get_bm25()
        self.bm25 = BM25Okapi(corpus)
        self._ready = True
        
        elapsed = time.time() - start
        print(f"   ✅ BM25 index ready: {len(corpus)} docs in {elapsed:.1f}s")
        
        # Save cache
        self._save_cache()
        
        return True
    
    def _save_cache(self):
        try:
            cache_data = {
                "doc_ids": self.doc_ids,
                "bm25": self.bm25,
                "doc_meta": self.doc_meta,
            }
            with open(self.cache_path, "wb") as f:
                pickle.dump(cache_data, f)
            print(f"   💾 Cache saved: {self.cache_path}")
        except Exception as e:
            print(f"   ⚠️ Cache save failed: {e}")
    
    def _load_cache(self):
        print(f"   📦 Loading BM25 cache...")
        start = time.time()
        with open(self.cache_path, "rb") as f:
            cache_data = pickle.load(f)
        self.doc_ids = cache_data["doc_ids"]
        self.bm25 = cache_data["bm25"]
        self.doc_meta = cache_data["doc_meta"]
        self._ready = True
        elapsed = time.time() - start
        print(f"   ✅ Cache loaded: {len(self.doc_ids)} docs in {elapsed:.1f}s")
        return True
    
    def search_bm25(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """BM25 search: trả về [(doc_id, score), ...]"""
        if not self._ready:
            return []
        
        tokens = tokenize_vi(query)
        if not tokens:
            return []
        
        scores = self.bm25.get_scores(tokens)
        
        # Top-K bằng argpartition (nhanh hơn argsort)
        import numpy as np
        if len(scores) <= top_k:
            top_indices = np.argsort(scores)[::-1]
        else:
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.doc_ids[idx], float(scores[idx])))
        
        return results[:top_k]
    
    def search_fts5(self, query: str, top_k: int = 50) -> List[int]:
        """FTS5 search: trả về [doc_id, ...] theo rank."""
        from app.routers.laws import parse_fts_query
        
        fts_query = parse_fts_query(query)
        if not fts_query:
            return []
        
        conn = sqlite3.connect(self.main_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, top_k)
            )
            results = [row[0] for row in cursor.fetchall()]
        except Exception:
            results = []
        finally:
            conn.close()
        
        return results
    
    def reciprocal_rank_fusion(
        self,
        bm25_results: List[Tuple[int, float]],
        fts5_results: List[int],
        k: int = 60,
        bm25_weight: float = 0.7,
        fts5_weight: float = 0.3,
    ) -> List[int]:
        """
        Reciprocal Rank Fusion: kết hợp ranking từ BM25 và FTS5.
        
        RRF Score = Σ weight / (k + rank)
        
        bm25_weight=0.7: BM25 quan trọng hơn vì scoring chính xác hơn
        """
        rrf_scores: Dict[int, float] = {}
        
        # BM25 results
        for rank, (doc_id, _score) in enumerate(bm25_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + bm25_weight / (k + rank + 1)
        
        # FTS5 results
        for rank, doc_id in enumerate(fts5_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + fts5_weight / (k + rank + 1)
        
        # Sort by RRF score
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _ in sorted_docs]
    
    def search(self, query: str, top_k: int = 10, retrieval_k: int = 50) -> List[Dict]:
        """
        Hybrid search: BM25 + FTS5 + RRF → top_k results với metadata.
        """
        if not self._ready:
            return []
        
        # Bước 1: Lấy kết quả từ cả 2 engine
        bm25_results = self.search_bm25(query, top_k=retrieval_k)
        fts5_results = self.search_fts5(query, top_k=retrieval_k)
        
        # Bước 2: RRF fusion
        fused_doc_ids = self.reciprocal_rank_fusion(bm25_results, fts5_results)
        
        # Bước 3: Enrich với metadata
        results = []
        for doc_id in fused_doc_ids[:top_k]:
            meta = self.doc_meta.get(doc_id, {})
            results.append({
                "id": doc_id,
                "title": meta.get("title", ""),
                "so_ky_hieu": meta.get("so_ky_hieu", ""),
                "loai_van_ban": meta.get("loai_van_ban", ""),
                "tinh_trang_hieu_luc": meta.get("tinh_trang_hieu_luc", ""),
                "co_quan_ban_hanh": meta.get("co_quan_ban_hanh", ""),
                "ngay_ban_hanh": meta.get("ngay_ban_hanh", ""),
            })
        
        return results
    
    @property
    def is_ready(self):
        return self._ready


# Singleton instance
_engine: Optional[HybridSearchEngine] = None

def get_hybrid_engine() -> Optional[HybridSearchEngine]:
    global _engine
    return _engine

def init_hybrid_engine(main_db: str, content_db: str) -> HybridSearchEngine:
    global _engine
    _engine = HybridSearchEngine(main_db, content_db)
    _engine.build_index()
    return _engine
