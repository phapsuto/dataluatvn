# 🧠 SYSTEM MEMORY — LuatBot RAG Pipeline
> **MỤC ĐÍCH**: File này lưu trữ toàn bộ tiến trình phát triển, bugs đã fix, bugs chưa fix, 
> và những gì CẦN LÀM TIẾP. Bất kỳ agent nào mở file này sẽ biết chính xác trạng thái hệ thống.
> 
> **CẬP NHẬT LẦN CUỐI**: 2026-06-15T17:40:00+10:00

---

## 📊 TRẠNG THÁI HIỆN TẠI

| Metric | Giá trị | Mục tiêu |
|--------|---------|----------|
| **Accuracy tổng** | ~95%+ (est. V21) | ≥ 95% |
| **Accuracy B** (hỏi xuôi) | 95.2% (119/125) | ✅ Đạt |
| **Accuracy C** (hỏi chủ đề) | 95.2% (119/125) | ✅ Đạt |
| **Accuracy D** (hỏi số hiệu) | ~95% (est. +3 fixed) | ✅ Est. Đạt |
| **Accuracy E** (tình huống) | 95.9% (93/97) | ✅ Đạt |
| **Avg Latency** | ~15s | < 10s |
| **LLM Model** | DeepSeek-V4-Flash | ✅ |
| **FAISS Index** | SQ8 (1.5 GB) | ✅ Quantized |
| **Server RAM** | **3.5 GB** (was 8.6) | ✅ -59% |
| **Error rate** | 0% | ✅ |

---

## 🏗️ KIẾN TRÚC HỆ THỐNG

```
User Query
    ↓
[1] Semantic Router (legal_router.py)
    → extract: year, doc_type, issuer, domain
    ↓
[2] Query Rewriter (query_rewriter.py) — LLM optimize search terms
    ↓
[3] Ultimate Retrieval Pipeline (ultimate_retrieval.py)
    ├── Step 0: Exact Match Boost (DB so_ky_hieu lookup)
    │   ├── Locality/Issuer Scoring 
    │   └── Symbol normalization (whitespace, parenthetical strip)
    ├── Step 0.1: Title/Entity Match (entity_extractor.py)
    ├── Step 0.1.5: Title FTS5 Match
    ├── Step 0.2: FTS5 Exact Phrase Boost (for text fragments)
    ├── Step 1: Hybrid Search (BM25 + FAISS dense)
    │   └── Dynamic RRF Weights
    ├── Step 2: Domain/Metadata Soft Boost
    │   └── Year, Doc Type, Issuer multipliers
    ├── Step 2.2: Boilerplate Penalty
    ├── Step 2.3: Text Fragment N-gram Overlap
    ├── Step 3: Graph Expansion (LightGraphManager)
    └── Step 4: FPT Cloud Reranker (bge-reranker-v2-m3)
    ↓
[4] FLARE RAG Generation (flare_retrieval.py)
    ├── Intent Classification → specialized prompt
    ├── Simple queries → direct stream
    └── Complex queries → draft → [SEARCH:...] → re-retrieve → final stream
    ↓
[5] LLM Gateway (llm_gateway.py) → FPT Cloud API
    ↓
[6] User Memory Save (user_memory.py)
```

### Database Files
| File | Size | Purpose |
|------|------|---------|
| vietnamese_legal_documents.db | ~9 GB | Main docs + chunks |
| vector_store.db | ~7.3 GB | FAISS metadata |
| content_store.db | ~3.3 GB | Full text content |
| chunks_faiss.index | ~6.4 GB | FAISS FP32 index |
| chunks_faiss_sq8.index | ~1.6 GB | FAISS SQ8 compressed |
| bm25_index.pkl | ~338 MB | BM25 sparse index |
| light_graph_store.db | ~304 MB | Citation graph |
| semantic_cache.db | ~35 MB | Query cache |
| user_session_memory.db | ~21 MB | User memory |
| admin.db | ~24 KB | Admin/API keys |

---

## 🐛 BUG ĐÃ TÌM THẤY (Session hiện tại)

### Bug 1: ✅ ĐÃ FIX — Router issuer extraction sai (CRITICAL)
- **File**: `app/utils/legal_router.py` dòng 249-260
- **Triệu chứng**: Query "do Ủy Ban Nhân Dân Tỉnh Nghệ An ban hành" → router extract `extracted_issuer = "Ủy"` (chỉ 1 chữ!)
- **Nguyên nhân**: Regex UBND matching nuốt "ban hành" vào match, cleanup cắt từ "ban" → chỉ còn "Ủy"
- **Fix**: Thêm `"do X ban hành"` priority regex + fix cleanup thêm `ban\s+hành`
- **Kết quả**: Fix 3/5 D-type failures (Nghệ An, Bình Định, Quảng Ngãi)

### Bug 5: ✅ ĐÃ FIX — Reranker bị TẮT ở server (CRITICAL)
- **File**: `server.py` dòng 16
- **Triệu chứng**: `DISABLE_RERANKER=1` được set cứng → direct test ĐÚNG nhưng API SAI
- **Fix**: Comment out `DISABLE_RERANKER=1`

### Bug 2: ✅ ĐÃ FIX — Graph expansion ×0.1 score (CRITICAL)  
- **File**: `app/utils/ultimate_retrieval.py` dòng 742
- **Triệu chứng**: `item["score"] = doc_score + score * 0.1` → exact match 1100 bị giảm thành 110
- **Fix**: Giữ nguyên score cho `is_exact_match` chunks

### Bug 3: ✅ ĐÃ FIX — Reranker overwrite score (CRITICAL)
- **File**: `app/utils/ultimate_retrieval.py` dòng 835
- **Triệu chứng**: FPT Reranker trả `relevance_score` (0-1) rồi OVERWRITE hoàn toàn score cũ → phá vỡ locality scoring
- **Fix**: Blend reranker score + original score thay vì overwrite

### Bug 4: ✅ ĐÃ FIX — Locality scoring + smart filter
- **File**: `app/utils/ultimate_retrieval.py` dòng 288-300
- **Fix**: Khi có strong issuer/locality match (score ≥ 100), chỉ lấy docs from matched issuer

---

## 🎯 D-TYPE FAILURES (10 câu, là nút thắt lên 95%)

| # | Symbol | Expected | Got | Province Expected | Root Cause |
|---|--------|----------|-----|-------------------|------------|
| 1 | 17/2001/QĐ-UB | 95201 | 70012 | Cần Thơ | DB symbol có space: "17  /2001/QĐ-UB" |
| 2 | 61/2024/QĐ-UBND | 172894 | 172603 | Nghệ An | Router extract issuer sai → Bug 1 |
| 3 | 50/2025/QĐ-UBND | 178541 | 184917 | Bạc Liêu | Symbol ko tồn tại cho tỉnh này? |
| 4 | 14/2006/QĐ-UBND | 60346 | 78901 | Bắc Giang | Router OK nhưng downstream override |
| 5 | 129/2005/QĐ-UBND | 41831 | ✅ | Quảng Ngãi | ĐÃ FIX |
| 6 | 28/2009/QĐ-UBND | 100815 | 89508 | Bình Định | Double-space in DB agency |
| 7 | 11/QĐ-UB-QLĐT | 98184 | 91418 | HCM | Unique suffix -QLĐT |
| 8 | 02/2018/QĐ-UBND | 136690 | 128237 | Sơn La | 38+ collision |
| 9 | 497/QĐ-UBND | 37243 | 31705 | Hải Phòng | Many collision |
| 10 | 22-HĐBT | 3315 | 3841 | Hội đồng BT | Historical doc |

---

## ✅ THAY ĐỔI ĐÃ ÁP DỤNG

### Model & Performance
1. `.env`: `FPT_CLOUD_DEFAULT_MODEL=DeepSeek-V4-Flash` (từ Qwen3-32B)
2. `app/utils/llm_gateway.py`: Thêm `max_tokens=1024` (giảm token waste)
3. `app/config.py`: Chuyển FAISS index FP32 → **SQ8** (RAM 8.6→3.5 GB)
4. `server.py`: Bỏ `DISABLE_RERANKER=1` → bật FPT Cloud Reranker

### Retrieval Fixes
5. `app/utils/legal_router.py`: Thêm `"do X ban hành"` priority regex + fix cleanup
6. `app/utils/ultimate_retrieval.py`:
   - Smart issuer/locality filter (dòng 291-303) — chỉ lấy docs match issuer khi score ≥ 100
   - Score propagation vào chunks (dòng 335) — `1000 + doc_score` thay vì flat 1000
   - Graph expansion preserve exact match score (dòng 742-746)
   - Reranker score blending (dòng 835-845) — blend thay vì overwrite

---

## 📋 VIỆC CẦN LÀM TIẾP

### Priority 1: Fix D-type → đạt 95%+ (CRITICAL)
- [x] **FIX Bug 1**: Thêm `"do X ban hành"` regex vào `legal_router.py` ✅
- [x] **FIX Bug 5**: Bật reranker (bỏ DISABLE_RERANKER=1) ✅
- [x] Validate: re-run D-type failures → 3/5 fixed ✅
- [/] Chạy full 100 câu benchmark V21 (SQ8) → ĐANG CHẠY

### Priority 2: Giảm RAM & latency
- [x] Chuyển FAISS FP32 → SQ8 (RAM 8.6→3.5 GB) ✅
- [ ] Profile retrieval bottleneck (BM25 vs DB vs reranker)
- [ ] Bật Semantic Cache cho hot queries

### Priority 3: Code cleanup
- [x] Review tất cả files cho dead code ✅
  - `semantic_cache_manager.py` = DEAD (không import ở đâu)
  - `query_expansion.py` = DISABLED (env var)
- [x] Kiểm tra tính năng enable/disable ✅
- [x] Verify Telegram bot, MCP server, admin pages ✅

### Priority 4: Report & Documentation
- [ ] Báo cáo 6 repos/datasets (3 GitHub + 3 HuggingFace)
- [ ] Cập nhật README.md
- [ ] Test 500 câu mới

---

## 📁 KEY FILES REFERENCE

| File | Lines | Purpose |
|------|-------|---------|
| `server.py` | ~200 | FastAPI app entry |
| `app/routers/chatbot.py` | ~383 | Main chat endpoint |
| `app/routers/laws.py` | ~2800 | Search API + models |
| `app/utils/ultimate_retrieval.py` | ~1011 | Core retrieval pipeline |
| `app/utils/flare_retrieval.py` | ~169 | FLARE RAG generation |
| `app/utils/legal_router.py` | ~314 | Intent routing |
| `app/utils/llm_gateway.py` | ~180 | LLM API wrapper |
| `app/utils/entity_extractor.py` | ~200 | Law title matching |
| `app/utils/light_graph_manager.py` | ~300 | Citation graph |
| `app/utils/semantic_cache_manager.py` | ~280 | Query caching |
| `app/utils/user_memory.py` | ~200 | User session memory |
| `telegram_bot.py` | ~1200 | Telegram integration |
| `mcp_server.py` | ~700 | MCP tool server |
