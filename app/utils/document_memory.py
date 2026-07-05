import faiss
import numpy as np
from typing import List, Dict, Any

# Session storage for Notebooks (in a real app, this would be Redis/DB + Vector DB cluster)
# Format: { notebook_id: { "index": faiss.Index, "chunks": [{"text": str, "source_id": str}] } }
_NOTEBOOK_STORE: Dict[str, Dict[str, Any]] = {}

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Simple character-based overlapping chunker for Vietnamese."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += (chunk_size - overlap)
    return chunks

def embed_texts(texts: List[str]) -> np.ndarray:
    """Uses the existing BGE-M3 model to embed texts."""
    from app.routers.laws import get_smart_search_resources
    model, _ = get_smart_search_resources()
    
    if hasattr(model, "encode"):
        embeddings = model.encode(texts, normalize_embeddings=True)
    elif hasattr(model, "embed_documents"): # for Langchain embeddings
        embeddings = np.array(model.embed_documents(texts))
    else:
        # Fallback if remote embedder
        embeddings = model.embed(texts)
        
    return np.array(embeddings).astype('float32')

def add_document_to_notebook(notebook_id: str, source_id: str, text: str):
    """Chunks a document and adds it to the FAISS index of the notebook."""
    chunks = chunk_text(text)
    if not chunks:
        return
        
    embeddings = embed_texts(chunks)
    
    if notebook_id not in _NOTEBOOK_STORE:
        d = embeddings.shape[1]
        index = faiss.IndexFlatIP(d) # Inner product = cosine similarity for normalized vectors
        _NOTEBOOK_STORE[notebook_id] = {
            "index": index,
            "chunks": []
        }
        
    store = _NOTEBOOK_STORE[notebook_id]
    store["index"].add(embeddings)
    
    for chunk in chunks:
        store["chunks"].append({"text": chunk, "source_id": source_id})

def search_notebook_docs(notebook_id: str, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Searches the notebook's documents for relevant chunks."""
    if notebook_id not in _NOTEBOOK_STORE:
        return []
        
    store = _NOTEBOOK_STORE[notebook_id]
    if store["index"].ntotal == 0:
        return []
        
    query_emb = embed_texts([query])
    distances, indices = store["index"].search(query_emb, min(top_k, store["index"].ntotal))
    
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx != -1:
            chunk = store["chunks"][idx]
            results.append({
                "text": chunk["text"],
                "source_id": chunk["source_id"],
                "score": float(dist)
            })
            
    return results
