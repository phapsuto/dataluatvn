import os
import sqlite3
import faiss
import numpy as np
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

# Setup paths
DATA_DIR = "data"
FAISS_DIR = os.path.join(DATA_DIR, "notebooks_faiss")
NOTEBOOK_DB = os.path.join(DATA_DIR, "notebooks.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "notebooks_uploads")

os.makedirs(FAISS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

def init_notebook_db():
    conn = sqlite3.connect(NOTEBOOK_DB)
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

def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 300) -> List[str]:
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    current_chunk = ""
    
    for p in paragraphs:
        if len(current_chunk) + len(p) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Simple overlap
            current_chunk = current_chunk[-overlap:] + "\n\n" + p
        else:
            current_chunk += ("\n\n" if current_chunk else "") + p
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
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
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
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
    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()
    # Due to ON DELETE CASCADE, sources and chunks will be deleted
    c.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    
    path = get_faiss_path(notebook_id)
    if os.path.exists(path):
        os.remove(path)
        
    return deleted

def update_notebook(notebook_id: str, updates: dict) -> Optional[dict]:
    conn = sqlite3.connect(NOTEBOOK_DB)
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
        
    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    c.execute(
        "INSERT INTO notebook_sources (id, notebook_id, filename, file_type, file_size, chunk_count, status, total_pages, processed_pages, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, notebook_id, filename, file_type, file_size, 0, "processing", 0, 0, now)
    )
    conn.commit()
    conn.close()

def update_source_progress(source_id: str, status: str, processed_pages: int = 0, total_pages: int = 0, chunk_count: int = 0):
    conn = sqlite3.connect(NOTEBOOK_DB)
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

def add_source_chunks(notebook_id: str, source_id: str, text: str) -> dict:
    chunks = chunk_text(text)
    if not chunks:
        update_source_progress(source_id, "error")
        return {"error": "Text is empty or could not be chunked"}
        
    embeddings = embed_texts(chunks)
    
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    
    # FAISS
    index = load_or_create_faiss(notebook_id, dim=embeddings.shape[1])
    ids_array = np.array(inserted_ids, dtype=np.int64)
    index.add_with_ids(embeddings, ids_array)
    save_faiss(notebook_id, index)
    
    # Update status to completed
    update_source_progress(source_id, "completed", processed_pages=0, total_pages=0, chunk_count=len(chunks))
    
    # Update notebook timestamp
    update_notebook(notebook_id, {})
    
    return {"status": "success", "source_id": source_id, "chunks": len(chunks)}

def add_source_text(notebook_id: str, source_id: str, text: str, filename: str = "text_upload") -> dict:
    chunks = chunk_text(text)
    if not chunks:
        return {"error": "Text is empty or could not be chunked"}
        
    # Ensure notebook exists
    if not get_notebook(notebook_id):
        create_notebook(notebook_id, "Untitled Notebook")
        
    embeddings = embed_texts(chunks)
    
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    
    # FAISS
    index = load_or_create_faiss(notebook_id, dim=embeddings.shape[1])
    ids_array = np.array(inserted_ids, dtype=np.int64)
    index.add_with_ids(embeddings, ids_array)
    save_faiss(notebook_id, index)
    
    # Update notebook timestamp
    update_notebook(notebook_id, {})
    
    return {"status": "success", "source_id": source_id, "chunks": len(chunks)}

def list_sources(notebook_id: str) -> List[dict]:
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM notebook_sources WHERE notebook_id = ? ORDER BY created_at DESC", (notebook_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_source_text(source_id: str) -> str:
    conn = sqlite3.connect(NOTEBOOK_DB)
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
        
    # Remove directly from FAISS without re-embedding
    if chunk_ids:
        path = get_faiss_path(notebook_id)
        if os.path.exists(path):
            index = faiss.read_index(path)
            ids_array = np.array(chunk_ids, dtype=np.int64)
            index.remove_ids(ids_array)
            faiss.write_index(index, path)
        
    update_notebook(notebook_id, {})
    return True

# --- Messages ---
def add_notebook_message(notebook_id: str, message_id: str, role: str, content: str, citations: list = None):
    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    citations_str = json.dumps(citations, ensure_ascii=False) if citations else None
    c.execute(
        "INSERT INTO notebook_messages (id, notebook_id, role, content, created_at, citations) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, notebook_id, role, content, now, citations_str)
    )
    conn.commit()
    conn.close()

# --- FAISS Search ---

def search_notebook_docs(notebook_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    path = get_faiss_path(notebook_id)
    if not os.path.exists(path):
        return []
        
    index = faiss.read_index(path)
    if index.ntotal == 0:
        return []
        
    query_emb = embed_texts([query])
    distances, indices = index.search(query_emb, min(top_k, index.ntotal))
    
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    valid_ids = [int(i) for i in indices[0] if i != -1]
    if not valid_ids:
        conn.close()
        return []
        
    placeholders = ",".join(["?"] * len(valid_ids))
    c.execute(f"""
        SELECT c.id, c.text, c.chunk_index, c.source_id, s.filename as filename 
        FROM notebook_chunks c
        JOIN notebook_sources s ON c.source_id = s.id
        WHERE c.id IN ({placeholders})
        AND c.notebook_id = ?
    """, valid_ids + [notebook_id])
    
    rows = c.fetchall()
    conn.close()
    
    # Map back to dict for fast lookup and preserving faiss order
    chunk_map = {r["id"]: dict(r) for r in rows}
    
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        idx_int = int(idx)
        if idx_int != -1 and idx_int in chunk_map:
            chunk = chunk_map[idx_int]
            score = float(dist)
            results.append({
                "text": chunk["text"],
                "source_id": chunk["source_id"],
                "filename": chunk["filename"],
                "chunk_index": chunk.get("chunk_index", 0),
                "score": score
            })
            
    return results

# --- Mindmaps ---

def create_mindmap(mindmap_id: str, notebook_id: str, title: str, data: str = "{}") -> dict:
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mindmaps WHERE notebook_id = ? ORDER BY created_at DESC", (notebook_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_mindmap(mindmap_id: str) -> Optional[dict]:
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mindmaps WHERE id = ?", (mindmap_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_mindmap(mindmap_id: str, updates: dict) -> Optional[dict]:
    conn = sqlite3.connect(NOTEBOOK_DB)
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
    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()
    c.execute("DELETE FROM mindmaps WHERE id = ?", (mindmap_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

