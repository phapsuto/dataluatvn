# 0001. Architecture: RAG Gen 3 with 5-Axis Persona

**Date**: 2026-07-24  
**Status**: Accepted  

## Context
Our user base ranges from general citizens to highly specialized roles (investigators, judges, lawyers). A one-size-fits-all LLM answer is often either too simplistic for professionals or too complex for citizens. Additionally, the sheer volume of legal documents (154k+) means pure vector search (FAISS) often returns irrelevant or outdated laws.

## Decision
We adopted the **RAG Gen 3** architecture with the following core pillars:
1. **Hybrid Retrieval**: BM25 (SQLite FTS5) for exact keyword/statute matching, combined with `BAAI/bge-m3` dense embeddings for semantic search.
2. **Semantic Caching**: To reduce latency and LLM costs, identical or semantically similar queries (>0.92 cosine similarity) are intercepted by a SQLite+FAISS cache layer.
3. **5-Axis Persona**: The UI explicitly allows the user to select their role (`nguoi_dan`, `cong_an`, `tham_phan`, `luat_su_doanh_nghiep`, `chuyen_vien_phap_ly`). This overrides the default system prompt, forcing the LLM to adopt the precise tone, jargon, and analytical framework suited for the user.
4. **LLM Agnosticism**: We route all calls through an `LLMGateway` (using `litellm` style wrappers) to allow hot-swapping between DeepSeek, Claude, or GPT-4 depending on quota and performance.

## Consequences
- **Positive**: Answers are highly tailored and accurate. Latency drops significantly for repeated queries.
- **Negative**: The backend logic is becoming complex. The `app/utils/` directory is increasingly tangled. We must enforce strict Facade patterns (Deep Modules) moving forward to prevent a "Ball of Mud" architecture.
