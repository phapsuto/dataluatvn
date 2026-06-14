import os
import sqlite3
import json
import re
import numpy as np
import logging

# Configure logger
logger = logging.getLogger("semantic_cache")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

class SemanticCacheManager:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SemanticCacheManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, db_path: str = "semantic_cache.db", threshold: float = 0.92):
        if self._initialized:
            return
        
        self.db_path = db_path
        self.threshold = threshold
        self.embedding_dim = 768  # Dimension of bkai-foundation-models/vietnamese-bi-encoder
        
        # Lazy imports for model & index
        self.model = None
        self.faiss_index = None
        self.cache_map = []  # Maps FAISS index position to SQLite record data
        
        # Initialize SQLite & build index
        self._init_db()
        self._build_faiss_index()
        
        self._initialized = True
        logger.info(f"✅ Semantic Cache Manager initialized with threshold {self.threshold}")
        
    def clean_query(self, query: str) -> str:
        if not query:
            return ""
        # Lowercase
        q = query.strip().lower()
        # Remove trailing punctuation like ?, ., !, etc.
        q = re.sub(r'[?.\!]+$', '', q)
        # Normalize whitespace
        q = re.sub(r'\s+', ' ', q).strip()
        return q
        
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT UNIQUE,
                response TEXT,
                citation_map TEXT,
                query_vector BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        
    def _lazy_load_model(self):
        if self.model is None:
            from app.routers.laws import get_smart_search_resources
            self.model, _ = get_smart_search_resources()
            if self.model is None:
                raise RuntimeError("Không thể tải mô hình nhúng để sử dụng cho Semantic Cache")
                
    def _build_faiss_index(self):
        import faiss
        
        # Initialize flat Inner Product index (equivalent to Cosine similarity if vectors are normalized)
        self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)
        self.cache_map = []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, query, response, citation_map, query_vector FROM semantic_cache")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            logger.info("ℹ️ Semantic Cache SQLite is empty. Initialized empty FAISS index.")
            return
            
        vectors = []
        for row in rows:
            rec_id, query, response, citation_map, vec_blob = row
            # Restore numpy array from blob
            vec = np.frombuffer(vec_blob, dtype=np.float32)
            if len(vec) == self.embedding_dim:
                vectors.append(vec)
                self.cache_map.append({
                    "id": rec_id,
                    "query": query,
                    "response": response,
                    "citation_map": json.loads(citation_map) if citation_map else {}
                })
                
        if vectors:
            vectors_np = np.vstack(vectors).astype(np.float32)
            # Normalize for cosine similarity
            faiss.normalize_L2(vectors_np)
            self.faiss_index.add(vectors_np)
            logger.info(f"✅ Loaded {len(self.cache_map)} records from SQLite into FAISS Cache Index.")

    def lookup(self, query: str) -> tuple[bool, str | None, dict | None]:
        """
        Looks up the query in the semantic cache.
        Returns:
            (is_hit, response, citation_map)
        """
        # Bắt buộc bypass cache nếu query chứa số hiệu văn bản hoặc điều khoản cụ thể
        # để tránh Cache Collision đối với các câu hỏi có cấu trúc giống nhau nhưng số hiệu khác nhau.
        if re.search(r'[Đđ]iều\s+\d+', query) or re.search(r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|\b\d+-[A-Za-zĐđÀ-ỹ]{2,}\b)', query):
            logger.info(f"⏭️ Semantic Cache BYPASS (contains document number or article): '{query}'")
            return False, None, None

        query = self.clean_query(query)
        if not query or not query.strip():
            return False, None, None
            
        try:
            import faiss
            
            # Ensure index has items
            if self.faiss_index is None or self.faiss_index.ntotal == 0:
                return False, None, None
                
            self._lazy_load_model()
            
            # Get embedding of query
            query_vector = self.model.encode([query]).astype(np.float32)
            faiss.normalize_L2(query_vector)
            
            # Search nearest neighbor
            distances, indices = self.faiss_index.search(query_vector, 1)
            
            best_score = float(distances[0][0])
            best_idx = int(indices[0][0])
            
            if best_idx != -1 and best_score >= self.threshold:
                record = self.cache_map[best_idx]
                logger.info(f"🎯 Semantic Cache HIT! Score: {best_score:.4f} for query: '{query}'")
                return True, record["response"], record["citation_map"]
                
            logger.info(f"💨 Semantic Cache MISS. Best Score: {best_score:.4f} for query: '{query}'")
            return False, None, None
            
        except Exception as e:
            logger.error(f"⚠️ Error during semantic cache lookup: {e}")
            return False, None, None
            
    def update(self, query: str, response: str, citation_map: dict):
        """
        Saves a query-response pair to the semantic cache database and index.
        """
        query = self.clean_query(query)
        if not query or not query.strip() or not response:
            return
            
        try:
            import faiss
            
            self._lazy_load_model()
            
            # Compute embedding vector
            query_vector = self.model.encode([query]).astype(np.float32)
            faiss.normalize_L2(query_vector)
            
            # Serialize vector to blob
            vec_blob = query_vector.tobytes()
            citation_str = json.dumps(citation_map, ensure_ascii=False)
            
            # Write to SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO semantic_cache (query, response, citation_map, query_vector) VALUES (?, ?, ?, ?)",
                    (query, response, citation_str, vec_blob)
                )
                conn.commit()
                rec_id = cursor.lastrowid
                
                # Update FAISS and memory cache map
                self.faiss_index.add(query_vector)
                self.cache_map.append({
                    "id": rec_id,
                    "query": query,
                    "response": response,
                    "citation_map": citation_map
                })
                logger.info(f"💾 Saved query '{query}' to semantic cache (ID: {rec_id})")
            except sqlite3.IntegrityError:
                # Query already exists in SQLite, just ignore or update
                pass
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"⚠️ Error updating semantic cache: {e}")

# Singleton helper
_cache_manager = None

def get_cache_manager(db_path: str = "semantic_cache.db", threshold: float = 0.92) -> SemanticCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = SemanticCacheManager(db_path=db_path, threshold=threshold)
    return _cache_manager
