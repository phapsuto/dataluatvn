import os
import sqlite3
import faiss
import numpy as np
from typing import List, Dict, Any, Optional
import json
import threading
from datetime import datetime

# Setup paths
DATA_DIR = "data"
FAISS_DIR = os.path.join(DATA_DIR, "notebooks_faiss")
NOTEBOOK_DB = os.path.join(DATA_DIR, "notebooks.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "notebooks_uploads")

os.makedirs(FAISS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- Connection & Lock Helpers ---
DB_TIMEOUT = 30  # seconds

def get_db_conn(db_path: str = None) -> sqlite3.Connection:
    """Create a SQLite connection with WAL mode and timeout for concurrent access."""
    conn = sqlite3.connect(db_path or NOTEBOOK_DB, timeout=DB_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30s busy timeout
    return conn

# Per-notebook FAISS file locks to prevent concurrent read/write corruption
_faiss_locks: Dict[str, threading.Lock] = {}
_faiss_locks_guard = threading.Lock()  # guard for _faiss_locks dict itself

def get_faiss_lock(notebook_id: str) -> threading.Lock:
    """Get or create a threading.Lock for a specific notebook's FAISS index."""
    with _faiss_locks_guard:
        if notebook_id not in _faiss_locks:
            _faiss_locks[notebook_id] = threading.Lock()
        return _faiss_locks[notebook_id]

def init_notebook_db():
    conn = get_db_conn()
    c = conn.cursor()
    # Notebooks
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebooks (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT,
            description TEXT,
            case_number TEXT,
            is_public INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    # Sources
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_sources (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            filename TEXT,
            file_type TEXT,
            file_size INTEGER,
            chunk_count INTEGER,
            status TEXT,
            total_pages INTEGER DEFAULT 0,
            processed_pages INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Chunks
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            notebook_id TEXT,
            chunk_index INTEGER,
            text TEXT,
            FOREIGN KEY (source_id) REFERENCES notebook_sources (id) ON DELETE CASCADE,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Messages
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_messages (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Mindmaps
    c.execute('''
        CREATE TABLE IF NOT EXISTS mindmaps (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            title TEXT,
            data TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Notebook Entities
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_entities (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            entity_type TEXT,
            entity_name TEXT,
            context TEXT,
            created_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Notebook Notes (persisted Studio Panel notes)
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_notes (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            title TEXT,
            type TEXT DEFAULT 'markdown',
            content TEXT,
            icon TEXT DEFAULT 'FileTextOutlined',
            color TEXT DEFAULT '#1a73e8',
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Entity Relationships (edges for Entity Graph)
    c.execute('''
        CREATE TABLE IF NOT EXISTS entity_relationships (
            id TEXT PRIMARY KEY,
            notebook_id TEXT,
            source_entity_id TEXT,
            target_entity_id TEXT,
            relation_type TEXT,
            description TEXT,
            created_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Notebook Extractions
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebook_extractions (
            notebook_id TEXT PRIMARY KEY,
            data_json TEXT,
            updated_at TEXT,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id) ON DELETE CASCADE
        )
    ''')
    # Migrate new columns if they don't exist
    try:
        c.execute("ALTER TABLE notebook_sources ADD COLUMN total_pages INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE notebook_sources ADD COLUMN processed_pages INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE notebook_messages ADD COLUMN citations TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE notebook_sources ADD COLUMN summary TEXT")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

# Initialize on module load
init_notebook_db()

def get_faiss_path(notebook_id: str) -> str:
    return os.path.join(FAISS_DIR, f"{notebook_id}.index")

def load_or_create_faiss(notebook_id: str, dim: int = 1024) -> faiss.Index:
    # 1024 is the embedding dimension for BGE-M3
    path = get_faiss_path(notebook_id)
    if os.path.exists(path):
        try:
            index = faiss.read_index(path)
            # Check if it's an old FlatIP without IDMap
            if not hasattr(index, 'add_with_ids'):
                raise ValueError("Old index format")
            return index
        except Exception:
            print(f"[FAISS] Recreating outdated index for {notebook_id}")
            os.remove(path)
            
    base_index = faiss.IndexFlatIP(dim)
    return faiss.IndexIDMap(base_index)

def save_faiss(notebook_id: str, index: faiss.Index):
    path = get_faiss_path(notebook_id)
    faiss.write_index(index, path)

import re

# Regex patterns for legal document structure detection
_HEADING_PATTERNS = re.compile(
    r'^(?:'
    r'(?:PHẦN|CHƯƠNG|MỤC|TIỂU MỤC)\s+[IVXLCDM\d]+'
    r'|Điều\s+\d+'
    r'|(?:^|\n)\s*(?:[IVXLCDM]+|\d+)\.\s+[A-ZÀ-Ỹ]'
    r'|^\s*(?:Khoản|Mục|Phần)\s+\d+'
    r'|^\s*[A-ZÀ-Ỹ][A-ZÀ-Ỹ\s]{5,}$'
    r')',
    re.MULTILINE | re.UNICODE
)

def _is_heading(line: str) -> bool:
    """Check if a line is a legal document heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return False
    return bool(_HEADING_PATTERNS.match(stripped))

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences, respecting Vietnamese punctuation."""
    # Split on sentence boundaries but keep the delimiter
    parts = re.split(r'(?<=[.!?;])\s+', text)
    return [p for p in parts if p.strip()]

def chunk_text(text: str, chunk_size: int = 2500, overlap: int = 500) -> List[str]:
    """Smart chunking that respects document structure.
    
    Strategy:
    1. Split by headings first (Điều, Chương, Mục, etc.)
    2. If a section is too long, split by paragraphs
    3. Never cut in the middle of a sentence
    4. Overlap preserves context between chunks
    """
    if not text or not text.strip():
        return [text] if text else []
    
    # Step 1: Split into structural sections by headings
    lines = text.split('\n')
    sections = []
    current_section = []
    
    for line in lines:
        if _is_heading(line) and current_section:
            sections.append('\n'.join(current_section))
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append('\n'.join(current_section))
    
    # Step 2: Process each section into chunks
    chunks = []
    current_chunk = ""
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
            
        # If adding this section fits in current chunk
        if len(current_chunk) + len(section) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + section
            continue
        
        # If current chunk is non-empty, save it first
        if current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of last chunk
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text
        
        # If section itself fits in a chunk, add it
        if len(section) <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + section
            continue
        
        # Section too long — split by paragraphs, then sentences
        paragraphs = [p.strip() for p in section.split('\n\n') if p.strip()]
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    current_chunk = overlap_text
                
                # If paragraph itself too long, split by sentences
                if len(para) > chunk_size:
                    sentences = _split_sentences(para)
                    for sent in sentences:
                        if len(current_chunk) + len(sent) + 1 <= chunk_size:
                            current_chunk += (" " if current_chunk else "") + sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                                current_chunk = overlap_text
                            current_chunk += (" " if current_chunk else "") + sent
                else:
                    current_chunk += ("\n\n" if current_chunk else "") + para
    
    if current_chunk and current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Deduplicate near-identical chunks (from overlap)
    if len(chunks) > 1:
        deduped = [chunks[0]]
        for c in chunks[1:]:
            # If chunk is >80% overlap with previous, skip
            if len(c) > 0 and len(deduped[-1]) > 0:
                overlap_ratio = len(set(c.split()) & set(deduped[-1].split())) / max(len(set(c.split())), 1)
                if overlap_ratio < 0.8:
                    deduped.append(c)
            else:
                deduped.append(c)
        chunks = deduped
    
    return chunks or [text]

def embed_texts(texts: List[str]) -> np.ndarray:
    from app.routers.laws import get_smart_search_resources
    model, _ = get_smart_search_resources()
    
    if hasattr(model, "encode"):
        embeddings = model.encode(texts, normalize_embeddings=True)
    elif hasattr(model, "embed_documents"):
        embeddings = np.array(model.embed_documents(texts))
    else:
        embeddings = model.embed(texts)
        
    return np.array(embeddings).astype('float32')

# --- CRUD Notebooks ---

def create_notebook(notebook_id: str, title: str, description: str = None, case_number: str = None, user_id: str = "default") -> dict:
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT OR REPLACE INTO notebooks (id, user_id, title, description, case_number, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (notebook_id, user_id, title, description, case_number, now, now)
    )
    conn.commit()
    conn.close()
    return get_notebook(notebook_id)

def get_notebook(notebook_id: str) -> Optional[dict]:
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,))
    row = c.fetchone()
    if not row:
        return None
    
    # Get stats
    c.execute("SELECT count(*) FROM notebook_sources WHERE notebook_id = ?", (notebook_id,))
    source_count = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM notebook_chunks WHERE notebook_id = ?", (notebook_id,))
    
    c.execute("SELECT id, role, content, created_at, citations FROM notebook_messages WHERE notebook_id = ? ORDER BY created_at ASC", (notebook_id,))
    messages_rows = c.fetchall()
    messages = []
    for m in messages_rows:
        m_dict = dict(m)
        if m_dict.get("citations"):
            try:
                m_dict["citations"] = json.loads(m_dict["citations"])
            except:
                m_dict["citations"] = []
        else:
            m_dict["citations"] = []
        messages.append(m_dict)
    
    conn.close()
    
    res = dict(row)
    res["sourceCount"] = source_count
    res["messageCount"] = len(messages)
    res["messages"] = messages
    res["isPublic"] = bool(res["is_public"])
    return res

def list_notebooks(user_id: str = "default") -> List[dict]:
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if user_id == "__all__":
        c.execute("SELECT id FROM notebooks ORDER BY updated_at DESC")
    else:
        c.execute("SELECT id FROM notebooks WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    notebooks = []
    for row in rows:
        nb = get_notebook(row["id"])
        if nb:
            notebooks.append(nb)
    return notebooks

def delete_notebook(notebook_id: str) -> bool:
    conn = get_db_conn()
    c = conn.cursor()
    conn.execute("PRAGMA foreign_keys=ON")  # Ensure CASCADE works
    c.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    
    path = get_faiss_path(notebook_id)
    if os.path.exists(path):
        os.remove(path)
        
    return deleted

def update_notebook(notebook_id: str, updates: dict) -> Optional[dict]:
    conn = get_db_conn()
    c = conn.cursor()
    
    fields = []
    values = []
    for k, v in updates.items():
        if k in ["title", "description", "case_number"]:
            fields.append(f"{k} = ?")
            values.append(v)
        elif k == "isPublic":
            fields.append("is_public = ?")
            values.append(1 if v else 0)
            
    if not fields:
        return get_notebook(notebook_id)
        
    fields.append("updated_at = ?")
    values.append(datetime.utcnow().isoformat())
    values.append(notebook_id)
    
    c.execute(f"UPDATE notebooks SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return get_notebook(notebook_id)

# --- CRUD Sources ---

def create_processing_source(notebook_id: str, source_id: str, filename: str, file_type: str, file_size: int):
    # Ensure notebook exists
    if not get_notebook(notebook_id):
        create_notebook(notebook_id, "Untitled Notebook")
        
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    c.execute(
        "INSERT INTO notebook_sources (id, notebook_id, filename, file_type, file_size, chunk_count, status, total_pages, processed_pages, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, notebook_id, filename, file_type, file_size, 0, "processing", 0, 0, now)
    )
    conn.commit()
    conn.close()

def update_source_progress(source_id: str, status: str, processed_pages: int = 0, total_pages: int = 0, chunk_count: int = 0):
    conn = get_db_conn()
    c = conn.cursor()
    
    if chunk_count > 0:
        c.execute(
            "UPDATE notebook_sources SET status = ?, processed_pages = ?, total_pages = ?, chunk_count = ? WHERE id = ?",
            (status, processed_pages, total_pages, chunk_count, source_id)
        )
    else:
        c.execute(
            "UPDATE notebook_sources SET status = ?, processed_pages = ?, total_pages = ? WHERE id = ?",
            (status, processed_pages, total_pages, source_id)
        )
    conn.commit()
    conn.close()

def update_source_summary(source_id: str, summary: str):
    """Update the auto-generated summary for a source."""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE notebook_sources SET summary = ? WHERE id = ?", (summary, source_id))
    conn.commit()
    conn.close()

def add_source_chunks(notebook_id: str, source_id: str, text: str) -> dict:
    chunks = chunk_text(text)
    if not chunks:
        update_source_progress(source_id, "error")
        return {"error": "Text is empty or could not be chunked"}
        
    embeddings = embed_texts(chunks)
    
    conn = get_db_conn()
    c = conn.cursor()
    
    inserted_ids = []
    for i, chunk in enumerate(chunks):
        c.execute(
            "INSERT INTO notebook_chunks (source_id, notebook_id, chunk_index, text) VALUES (?, ?, ?, ?)",
            (source_id, notebook_id, i, chunk)
        )
        inserted_ids.append(c.lastrowid)
        
    conn.commit()
    conn.close()
    
    # FAISS — use lock to prevent concurrent write corruption
    with get_faiss_lock(notebook_id):
        index = load_or_create_faiss(notebook_id, dim=embeddings.shape[1])
        ids_array = np.array(inserted_ids, dtype=np.int64)
        index.add_with_ids(embeddings, ids_array)
        save_faiss(notebook_id, index)
    
    # Update status to completed
    update_source_progress(source_id, "completed", processed_pages=0, total_pages=0, chunk_count=len(chunks))
    
    # Update notebook timestamp
    update_notebook(notebook_id, {})
    
    return {"status": "success", "source_id": source_id, "chunks": len(chunks)}

# --- Entities ---
def add_notebook_entity(notebook_id: str, entity_type: str, entity_name: str, context: str = "") -> dict:
    import uuid
    entity_id = f"ent_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().isoformat()
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO notebook_entities (id, notebook_id, entity_type, entity_name, context, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, notebook_id, entity_type, entity_name, context, created_at)
        )
        conn.commit()
        return {"status": "success", "entity_id": entity_id}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def get_notebook_entities(notebook_id: str) -> List[dict]:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id, entity_type, entity_name, context, created_at FROM notebook_entities WHERE notebook_id = ? ORDER BY created_at ASC", (notebook_id,))
        rows = c.fetchall()
        return [{"id": r[0], "type": r[1], "name": r[2], "context": r[3], "created_at": r[4]} for r in rows]
    finally:
        conn.close()

def add_source_text(notebook_id: str, source_id: str, text: str, filename: str = "text_upload") -> dict:
    chunks = chunk_text(text)
    if not chunks:
        return {"error": "Text is empty or could not be chunked"}
        
    # Ensure notebook exists
    if not get_notebook(notebook_id):
        create_notebook(notebook_id, "Untitled Notebook")
        
    embeddings = embed_texts(chunks)
    
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    c.execute(
        "INSERT INTO notebook_sources (id, notebook_id, filename, file_type, file_size, chunk_count, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, notebook_id, filename, "text/plain", len(text), len(chunks), "completed", now)
    )
    
    inserted_ids = []
    for i, chunk in enumerate(chunks):
        c.execute(
            "INSERT INTO notebook_chunks (source_id, notebook_id, chunk_index, text) VALUES (?, ?, ?, ?)",
            (source_id, notebook_id, i, chunk)
        )
        inserted_ids.append(c.lastrowid)
        
    conn.commit()
    conn.close()
    
    # FAISS — use lock to prevent concurrent write corruption
    with get_faiss_lock(notebook_id):
        index = load_or_create_faiss(notebook_id, dim=embeddings.shape[1])
        ids_array = np.array(inserted_ids, dtype=np.int64)
        index.add_with_ids(embeddings, ids_array)
        save_faiss(notebook_id, index)
    
    # Update notebook timestamp
    update_notebook(notebook_id, {})
    
    return {"status": "success", "source_id": source_id, "chunks": len(chunks)}

def list_sources(notebook_id: str) -> List[dict]:
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM notebook_sources WHERE notebook_id = ? ORDER BY created_at DESC", (notebook_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_source_text(source_id: str) -> str:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT text FROM notebook_chunks WHERE source_id = ? ORDER BY chunk_index ASC", (source_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return ""
    # We join by double newline but remember there is overlap.
    # It's fine for viewing purposes, or we can just join by space.
    return "\n\n...[Tiếp tục]...\n\n".join([r[0] for r in rows])

def delete_source(notebook_id: str, source_id: str) -> bool:
    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()
    
    # Get IDs of chunks belonging to this source
    c.execute("SELECT id FROM notebook_chunks WHERE source_id = ?", (source_id,))
    rows = c.fetchall()
    chunk_ids = [r[0] for r in rows]
    
    # Delete chunks from DB first
    c.execute("DELETE FROM notebook_chunks WHERE source_id = ?", (source_id,))
    
    c.execute("DELETE FROM notebook_sources WHERE id = ?", (source_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    
    if not deleted:
        return False
        
    # Remove directly from FAISS without re-embedding — use lock
    if chunk_ids:
        with get_faiss_lock(notebook_id):
            path = get_faiss_path(notebook_id)
            if os.path.exists(path):
                index = faiss.read_index(path)
                ids_array = np.array(chunk_ids, dtype=np.int64)
                index.remove_ids(ids_array)
                faiss.write_index(index, path)
    
    # Cleanup physical uploaded file
    upload_dir = os.path.join(UPLOADS_DIR, notebook_id)
    if os.path.exists(upload_dir):
        for fname in os.listdir(upload_dir):
            if fname.startswith(f"{source_id}_"):
                try:
                    os.remove(os.path.join(upload_dir, fname))
                except OSError:
                    pass
        
    update_notebook(notebook_id, {})
    return True

# --- Messages ---
def add_notebook_message(notebook_id: str, message_id: str, role: str, content: str, citations: list = None):
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    citations_str = json.dumps(citations, ensure_ascii=False) if citations else None
    c.execute(
        "INSERT INTO notebook_messages (id, notebook_id, role, content, created_at, citations) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, notebook_id, role, content, now, citations_str)
    )
    conn.commit()
    conn.close()

def clear_notebook_messages(notebook_id: str):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("DELETE FROM notebook_messages WHERE notebook_id = ?", (notebook_id,))
    conn.commit()
    conn.close()


# --- FAISS Search ---

def search_notebook_docs(notebook_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Hybrid search: FAISS vector + BM25 keyword, merged via Reciprocal Rank Fusion.
    Also expands results with adjacent chunks for full context."""
    
    path = get_faiss_path(notebook_id)
    
    # Load all chunks for this notebook (needed for BM25)
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT c.id, c.text, c.chunk_index, c.source_id, s.filename as filename 
        FROM notebook_chunks c
        JOIN notebook_sources s ON c.source_id = s.id
        WHERE c.notebook_id = ?
        ORDER BY c.source_id, c.chunk_index
    """, (notebook_id,))
    all_chunks = [dict(r) for r in c.fetchall()]
    conn.close()
    
    if not all_chunks:
        return []
    
    chunk_map = {ch["id"]: ch for ch in all_chunks}
    
    # === 1. FAISS Vector Search ===
    faiss_ranked = {}  # chunk_id -> rank (0-indexed)
    if os.path.exists(path):
        index = faiss.read_index(path)
        if index.ntotal > 0:
            query_emb = embed_texts([query])
            n_search = min(top_k * 2, index.ntotal)
            distances, indices = index.search(query_emb, n_search)
            
            rank = 0
            for dist, idx in zip(distances[0], indices[0]):
                idx_int = int(idx)
                if idx_int != -1 and idx_int in chunk_map:
                    faiss_ranked[idx_int] = rank
                    chunk_map[idx_int]["faiss_score"] = float(dist)
                    rank += 1
    
    # === 2. BM25 Keyword Search ===
    bm25_ranked = {}  # chunk_id -> rank (0-indexed)
    try:
        from rank_bm25 import BM25Okapi
        
        # Tokenize: simple whitespace + lowercase for Vietnamese
        def tokenize(text: str) -> List[str]:
            return text.lower().split()
        
        corpus = [tokenize(ch["text"]) for ch in all_chunks]
        bm25 = BM25Okapi(corpus)
        query_tokens = tokenize(query)
        bm25_scores = bm25.get_scores(query_tokens)
        
        # Get top results by BM25 score
        scored_indices = sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)
        for rank, (idx, score) in enumerate(scored_indices[:top_k * 2]):
            if score > 0:
                chunk_id = all_chunks[idx]["id"]
                bm25_ranked[chunk_id] = rank
                chunk_map[chunk_id]["bm25_score"] = float(score)
    except Exception as e:
        print(f"[BM25] Skipped: {e}")
    
    # === 3. Reciprocal Rank Fusion (RRF) ===
    # Merge FAISS and BM25 rankings — k=60 is standard
    RRF_K = 60
    all_candidate_ids = set(faiss_ranked.keys()) | set(bm25_ranked.keys())
    
    rrf_scores = {}
    for chunk_id in all_candidate_ids:
        score = 0.0
        if chunk_id in faiss_ranked:
            score += 1.0 / (RRF_K + faiss_ranked[chunk_id])
        if chunk_id in bm25_ranked:
            score += 1.0 / (RRF_K + bm25_ranked[chunk_id])
        rrf_scores[chunk_id] = score
    
    # Sort by RRF score descending
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # === 4. Adjacent Chunk Expansion ===
    # For top matches, also include neighboring chunks for context
    expanded_ids = set()
    # Build index for fast neighbor lookup: (source_id, chunk_index) -> chunk_id
    neighbor_index = {}
    for ch in all_chunks:
        neighbor_index[(ch["source_id"], ch["chunk_index"])] = ch["id"]
    
    for chunk_id in sorted_ids[:top_k]:
        expanded_ids.add(chunk_id)
        ch = chunk_map[chunk_id]
        sid = ch["source_id"]
        cidx = ch["chunk_index"]
        # Add previous and next chunk if they exist
        prev_key = (sid, cidx - 1)
        next_key = (sid, cidx + 1)
        if prev_key in neighbor_index:
            expanded_ids.add(neighbor_index[prev_key])
        if next_key in neighbor_index:
            expanded_ids.add(neighbor_index[next_key])
    
    # Build final results, maintaining RRF order for primary matches
    # Adjacent chunks get a slightly lower score
    results = []
    seen = set()
    
    for chunk_id in sorted_ids:
        if chunk_id in expanded_ids and chunk_id not in seen:
            ch = chunk_map[chunk_id]
            results.append({
                "text": ch["text"],
                "source_id": ch["source_id"],
                "filename": ch["filename"],
                "chunk_index": ch.get("chunk_index", 0),
                "score": rrf_scores.get(chunk_id, 0),
            })
            seen.add(chunk_id)
    
    # Add adjacent-only chunks (not in top RRF results)
    for chunk_id in expanded_ids:
        if chunk_id not in seen:
            ch = chunk_map[chunk_id]
            # Give adjacent chunks a base score
            parent_score = max(
                rrf_scores.get(neighbor_index.get((ch["source_id"], ch["chunk_index"] - 1), -1), 0),
                rrf_scores.get(neighbor_index.get((ch["source_id"], ch["chunk_index"] + 1), -1), 0),
            )
            results.append({
                "text": ch["text"],
                "source_id": ch["source_id"],
                "filename": ch["filename"],
                "chunk_index": ch.get("chunk_index", 0),
                "score": parent_score * 0.7,  # Adjacent chunks get 70% of parent score
            })
            seen.add(chunk_id)
    
    # Sort final results by score
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return results[:top_k]

# --- Mindmaps ---

def add_entity_relationship(notebook_id: str, source_id: str, target_id: str, rel_type: str, desc: str = "") -> str:
    conn = get_db_conn()
    c = conn.cursor()
    rel_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    c.execute(
        "INSERT INTO entity_relationships (id, notebook_id, source_entity_id, target_entity_id, relation_type, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rel_id, notebook_id, source_id, target_id, rel_type, desc, now)
    )
    conn.commit()
    conn.close()
    return rel_id

def save_notebook_extraction(notebook_id: str, data_json: str):
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    # Upsert logic (SQLite >= 3.24)
    c.execute("""
        INSERT INTO notebook_extractions (notebook_id, data_json, updated_at) 
        VALUES (?, ?, ?)
        ON CONFLICT(notebook_id) DO UPDATE SET 
            data_json=excluded.data_json, 
            updated_at=excluded.updated_at
    """, (notebook_id, data_json, now))
    conn.commit()
    conn.close()

def get_notebook_extraction(notebook_id: str) -> Optional[str]:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT data_json FROM notebook_extractions WHERE notebook_id = ?", (notebook_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def create_mindmap(mindmap_id: str, notebook_id: str, title: str, data: str = "{}") -> dict:
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO mindmaps (id, notebook_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (mindmap_id, notebook_id, title, data, now, now)
    )
    conn.commit()
    conn.close()
    return get_mindmap(mindmap_id)

def get_mindmaps(notebook_id: str) -> List[dict]:
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mindmaps WHERE notebook_id = ? ORDER BY created_at DESC", (notebook_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_mindmap(mindmap_id: str) -> Optional[dict]:
    conn = get_db_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mindmaps WHERE id = ?", (mindmap_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_mindmap(mindmap_id: str, updates: dict) -> Optional[dict]:
    conn = get_db_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values())
    
    if set_clause:
        set_clause += ", updated_at = ?"
        values.append(now)
        values.append(mindmap_id)
        
        c.execute(f"UPDATE mindmaps SET {set_clause} WHERE id = ?", values)
        conn.commit()
    
    conn.close()
    return get_mindmap(mindmap_id)

def delete_mindmap(mindmap_id: str) -> bool:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("DELETE FROM mindmaps WHERE id = ?", (mindmap_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ── Notebook Notes CRUD ──

def create_notebook_note(notebook_id: str, note_id: str, title: str, note_type: str = 'markdown',
                         content: str = '', icon: str = 'FileTextOutlined', color: str = '#1a73e8') -> dict:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            "INSERT OR REPLACE INTO notebook_notes (id, notebook_id, title, type, content, icon, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (note_id, notebook_id, title, note_type, content, icon, color, now, now)
        )
        conn.commit()
        return {"id": note_id, "notebook_id": notebook_id, "title": title, "type": note_type,
                "content": content, "icon": icon, "color": color, "created_at": now, "updated_at": now}
    finally:
        conn.close()

def list_notebook_notes(notebook_id: str) -> List[dict]:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id, title, type, content, icon, color, created_at, updated_at FROM notebook_notes WHERE notebook_id = ? ORDER BY created_at DESC", (notebook_id,))
        rows = c.fetchall()
        return [{"id": r[0], "title": r[1], "type": r[2], "content": r[3], "icon": r[4], "color": r[5], "created_at": r[6], "updated_at": r[7]} for r in rows]
    finally:
        conn.close()

def update_notebook_note(note_id: str, updates: dict) -> Optional[dict]:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        updates['updated_at'] = now
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [note_id]
        c.execute(f"UPDATE notebook_notes SET {set_clause} WHERE id = ?", values)
        conn.commit()
        c.execute("SELECT id, notebook_id, title, type, content, icon, color, created_at, updated_at FROM notebook_notes WHERE id = ?", (note_id,))
        row = c.fetchone()
        if row:
            return {"id": row[0], "notebook_id": row[1], "title": row[2], "type": row[3],
                    "content": row[4], "icon": row[5], "color": row[6], "created_at": row[7], "updated_at": row[8]}
        return None
    finally:
        conn.close()

def delete_notebook_note(note_id: str) -> bool:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM notebook_notes WHERE id = ?", (note_id,))
        deleted = c.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


# ── Entity Relationships CRUD ──

def add_entity_relationship(notebook_id: str, source_entity_id: str, target_entity_id: str,
                            relation_type: str, description: str = "") -> dict:
    import uuid
    rel_id = f"rel_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().isoformat()
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO entity_relationships (id, notebook_id, source_entity_id, target_entity_id, relation_type, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rel_id, notebook_id, source_entity_id, target_entity_id, relation_type, description, created_at)
        )
        conn.commit()
        return {"id": rel_id, "source": source_entity_id, "target": target_entity_id, "type": relation_type}
    finally:
        conn.close()

def get_entity_relationships(notebook_id: str) -> List[dict]:
    conn = get_db_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id, source_entity_id, target_entity_id, relation_type, description FROM entity_relationships WHERE notebook_id = ?", (notebook_id,))
        rows = c.fetchall()
        return [{"id": r[0], "source": r[1], "target": r[2], "type": r[3], "description": r[4]} for r in rows]
    finally:
        conn.close()

