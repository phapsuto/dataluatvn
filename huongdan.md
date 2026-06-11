# 📖 Hướng Dẫn Chi Tiết: Audit, Kiểm Thử & Chạy Benchmark (luatvietnam)

Tài liệu này cung cấp hướng dẫn chi tiết về quy trình chạy kiểm thử (Unit Tests), chạy đánh giá hiệu năng (Benchmark) trên 500 câu hỏi vàng, và tóm tắt kết quả của đợt dọn dẹp (Audit & Cleanup) mã nguồn toàn diện.

---

## 🧹 1. Kết Quả Audit & Dọn Dẹp Mã Nguồn
Để chuẩn hóa kho mã nguồn của dự án và loại bỏ hoàn toàn các tệp tin tạm thời, mã nguồn dư thừa, chúng tôi đã tiến hành quét và dọn dẹp toàn diện:

### A. Dọn Dẹp Thư Mục `scratch/`
*   **Tổng số file rác đã xóa**: Hơn **110 script thử nghiệm, log ghi nhận và patch thừa** (ví dụ: `test_flare.py`, `debug_reconstruct.py`, `rag_guardrails.py`,...).
*   **Danh sách tệp tin cốt lõi được GIỮ LẠI trong `scratch/`**:
    1.  `benchmark_gold_500.json`: Bộ dữ liệu 500 câu hỏi test thực tế với Ground Truth được chuẩn hóa.
    2.  `benchmark_gold_500_backup.json`: Bản sao lưu dự phòng cho bộ dữ liệu vàng.
    3.  `run_hybrid_benchmark_500.py`: Script khởi chạy benchmark chính thức.
    4.  `nhatky.md`: Nhật ký phát triển chi tiết qua từng Phase.
    5.  `bao_cao_vector.md`: Báo cáo chi tiết về tiến trình sinh vector chunks (1.55 triệu vector).
    6.  `audit_and_cleanup_plan.md`: Kế hoạch audit ban đầu của dự án.
    7.  `KE_HOACH_XAY_DUNG_DATA_PHAP_LUAT.md`: Định hướng xây dựng cơ sở dữ liệu pháp luật.

### B. Chuẩn Hóa Mã Nguồn & Sửa Lỗi
*   **Khắc phục lỗi import trong `app/query_expansion.py`**: Bổ sung import thiếu cho `Optional` từ module `typing`, loại bỏ nguy cơ gặp lỗi `NameError` khi phân tích type hints.
*   **Chuẩn hóa Pydantic v2**:
    *   Sửa đổi `Field(..., example=...)` thành `Field(..., json_schema_extra={"example": ...})` trong `app/schemas/auth.py`.
    *   Thay thế lớp cấu hình lỗi thời `class Config` bằng `model_config = ConfigDict(populate_by_name=True)` trong `app/routers/lineage.py`.
*   **Thiết lập thread-safety cho macOS**: Cấu hình các biến môi trường đơn luồng (`OMP_NUM_THREADS=1`,...) tại file khởi chạy `server.py` và `run_hybrid_benchmark_500.py` để ngăn chặn triệt để lỗi sập bộ nhớ `Segmentation Fault (exit code 139)`.

---

## 🧪 2. Hướng Dẫn Chạy Kiểm Thử Chức Năng (Unit Tests)
Dự án đã được cấu hình bộ kiểm thử chuẩn sử dụng `pytest`. Tất cả các tệp kiểm thử tự động đã được chuyển về thư mục `tests/`.

### Cách chạy:
Để chạy toàn bộ unit tests, di chuyển đến thư mục gốc của dự án và chạy lệnh:
```bash
pytest
```

### Các module được kiểm thử:
1.  **`tests/test_query_expansion.py`**: Kiểm tra cơ chế tự động mở rộng truy vấn thông qua LLM FPT Cloud (Gemma-4) và cơ chế đọc/ghi cache SQLite (1.2ms) cực nhanh để tối ưu chi phí API.
2.  **`tests/test_smart_search.py`**: Kiểm tra toàn diện các tầng tính toán trong Smart Search:
    *   *Metadata Filtering*: Lọc cứng bằng SQL theo loại văn bản, cơ quan ban hành, lĩnh vực.
    *   *Symbol Boosting*: Đẩy điểm xếp hạng vượt trội (+3.0) khi câu hỏi trùng số hiệu văn bản pháp luật.
    *   *Status Boosting*: Ưu tiên các văn bản còn hiệu lực pháp lý.
    *   *Semantic Reranking*: Sử dụng tích vô hướng trên GPU MPS để rerank Top-40 ứng viên dựa trên độ tương đồng Cosine chuẩn hóa.

---

## 📊 3. Hướng Dẫn Chạy Benchmark Đánh Giá Chất Lượng
Script benchmark sẽ so sánh trực tiếp 3 thuật toán tìm kiếm trên bộ 500 câu hỏi test thực tế.

### Lệnh chạy chính thức (Bắt buộc thiết lập biến môi trường để an toàn luồng):
```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 scratch/run_hybrid_benchmark_500.py
```

| Phương Pháp Tìm Kiếm | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | Latency (Độ trễ trung bình) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Document-level FTS5 (Baseline)** | 62.6% | 75.8% | 80.2% | 83.2% | 0.702 | **2.1 ms** |
| **Chunk-level FTS5 (Phase 1)** | 77.0% | 88.8% | 91.6% | 93.6% | 0.830 | **3.5 ms** |
| **SOTA Hybrid Search (BGE-M3 + FTS5 + Fusion + Reranker)** | **91.2%** | **96.4%** | **97.6%** | **98.4%** | **0.932** | **56.4 ms** |

### 💡 Đánh giá hiệu năng SOTA:
1.  **Chất lượng vượt trội (Recall Hit@10 đạt 98.4%)**: Phương pháp **SOTA Hybrid Search** tăng độ phủ chính xác tìm kiếm (Hit@10) lên **98.4%** (tăng mạnh từ **83.8%** của phiên bản cũ) và **MRR@10 đạt 0.932**, chứng minh chất lượng vượt bậc của việc chuyển từ mô hình cũ sang BAAI/bge-m3 kết hợp cùng AITeamVN/Vietnamese_Reranker.
2.  **Tối ưu hóa độ trễ (Latency ~56.4ms)**: Mặc dù sử dụng mô hình BGE-M3 nặng hơn và Cross-Encoder Reranker chấm điểm lại Top-40, nhờ cấu hình chạy **float16** trên Apple Silicon MPS GPU, độ trễ trung bình của Hybrid Search được kiểm soát tốt ở mức **56.4ms** (thấp hơn nhiều so với ngưỡng yêu cầu 150ms).
3.  **Normalized Score Fusion**: Thay đổi từ thuật toán RRF (Rank Reciprocal Fusion) sang kết hợp Min-Max normalized score (`0.3 * Sparse + 0.7 * Dense`) giúp giữ nguyên trọng số liên quan thực tế và cải thiện kết quả rõ rệt.
4.  **Offline-ready**: Tận dụng triệt để bộ nhớ cache Hugging Face thông qua cờ `HF_HUB_OFFLINE=1` giúp loại bỏ hoàn toàn các cuộc gọi kiểm tra mạng khi khởi tạo và hot-reload, loại bỏ hoàn toàn lỗi trễ mạng.
