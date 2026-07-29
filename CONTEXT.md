# Ubiquitous Language & Domain Model (DataLuatVN)

This document defines the shared language and architectural constraints for the **DataLuatVN** project. AI agents and human developers MUST use these exact terms when discussing the system, naming variables, and structuring code.

## 1. Core Domain Dictionary (Từ điển Thuật ngữ)

- **RAG Gen 3**: The current architecture of the application. It consists of Intent Routing, 5-Axis Persona, Hybrid Retrieval, Semantic Caching, Reranking, FLARE Speculative Generation, and Precedent/Adversarial Reasoning.
- **5-Axis Persona**: The system of assigning a specific role/lens to the AI before answering: `nguoi_dan` (default), `cong_an`, `tham_phan`, `luat_su_doanh_nghiep`, `chuyen_vien_phap_ly`.
- **Hybrid Search**: The combination of FTS5 (BM25) sparse retrieval in SQLite and `BAAI/bge-m3` dense vector retrieval in FAISS.
- **Semantic Cache**: The SQLite+FAISS caching layer that intercepts identical or highly semantically similar queries before hitting the LLM. 
- **Precedent Matcher**: The logic that matches similar Court Decisions (Bản án) or Precedents (Án lệ) to a user query. Note: A "Precedent" (Án lệ) is an officially recognized court decision by the Supreme Court. A "Court Decision" (Bản án) is just a regular ruling.
- **Adversarial Reasoning**: The module that forces the LLM to analyze the case from opposing perspectives (e.g., Plaintiff vs. Defendant) before drawing a conclusion.
- **Lineage Tree**: The cross-reference graph (Graph Database in SQLite) tracking how laws modify, replace, or guide each other.
- **FLARE (Forward-Looking Active REtrieval)**: A speculative generation technique where the AI drafts an answer, and if it lacks confidence, it triggers another retrieval mid-generation.

## 2. Architectural Constraints (Ràng buộc Kiến trúc)

1. **Deep Modules**: The code in `app/utils/` must expose simple interfaces (Facades) while hiding complex implementations. For example, `ultimate_retrieval.py` should expose a single `hybrid_retrieve()` function rather than forcing the router to coordinate FTS5, BGE-M3, and FlashRank manually.
2. **Stateless API**: All FastAPI endpoints in `app/routers/` must remain stateless. Any session memory must be passed explicitly via `session_id` and handled by the memory store.
3. **LLM Agnosticism**: The system uses `LLMGateway` (via `litellm` or direct wrappers). We do not hardcode OpenAI or Gemini APIs directly in the business logic.
4. **No UI Auto-Followups**: We do NOT hardcode follow-up suggestions using string matching. Let the LLM natively generate follow-up questions at the end of its response.

## 3. Workflow & AI Coding Rules

- **Red-Green-Refactor**: When fixing bugs or adding new features, write a failing `pytest` first.
- **Before modifying architecture**: Update this `CONTEXT.md` and create a new ADR in `docs/adr/`.
- **Variable Naming**: Always use the terms defined in Section 1. Do not invent new names like `ContextualCache` (use `SemanticCache`). Do not use `RoleSelector` (use `PersonaSwitcher` or `5-Axis Persona`).
