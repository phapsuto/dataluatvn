import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger("reranker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

class LightweightReranker:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LightweightReranker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        if self._initialized:
            return
            
        self.model_name = model_name
        self.ranker = None
        self._initialized = True
        logger.info(f"Initialized LightweightReranker config for model: {self.model_name}")
        
    def _lazy_load_ranker(self):
        if self.ranker is None:
            try:
                from flashrank import Ranker
                # Set cache directory to avoid writing to user home directory directly if possible,
                # otherwise flashrank handles it automatically
                self.ranker = Ranker(model_name=self.model_name, cache_dir="./.flashrank_cache")
                logger.info(f"✅ Loaded FlashRank model: {self.model_name} successfully.")
            except Exception as e:
                logger.error(f"❌ Failed to load FlashRank ranker: {e}")
                raise e
                
    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Reranks a list of chunk dicts based on their relevance to the query.
        Each chunk dict should contain 'chunk_text'.
        Returns the sorted list of chunks with an added 'score' field.
        """
        if not chunks:
            return []
            
        if not query or not query.strip():
            return chunks[:top_n]
            
        try:
            self._lazy_load_ranker()
            
            # Format passages for FlashRank: [{"id": idx, "text": "..."}]
            passages = []
            for idx, chunk in enumerate(chunks):
                text = chunk.get("chunk_text") or chunk.get("text") or ""
                passages.append({
                    "id": idx,
                    "text": text
                })
                
            from flashrank import RerankRequest
            request = RerankRequest(query=query, passages=passages)
            
            # Run FlashRank reranking
            rerank_results = self.ranker.rerank(request)
            
            # Reconstruct chunk list based on reranked passages
            reranked_chunks = []
            for item in rerank_results:
                idx = item["id"]
                score = float(item["score"])
                
                original_chunk = chunks[idx].copy()
                original_chunk["score"] = score
                reranked_chunks.append(original_chunk)
                
            logger.info(f"⚡ Reranked {len(chunks)} chunks to top {len(reranked_chunks[:top_n])} using FlashRank.")
            return reranked_chunks[:top_n]
            
        except Exception as e:
            logger.error(f"⚠️ Reranking failed: {e}. Falling back to default top_n order.")
            # Fallback to returning original top_n chunks and assign a default score
            fallback_chunks = []
            for chunk in chunks[:top_n]:
                c = chunk.copy()
                if "score" not in c:
                    c["score"] = 0.5
                fallback_chunks.append(c)
            return fallback_chunks

# Singleton helper
_reranker_instance = None

def get_reranker(model_name: str = "ms-marco-TinyBERT-L-2-v2") -> LightweightReranker:
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = LightweightReranker(model_name=model_name)
    return _reranker_instance
