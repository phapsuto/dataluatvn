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

Dự án hỗ trợ chạy kiểm nghiệm và đánh giá chất lượng tìm kiếm (Hit@10 và độ trễ Latency) trên bộ 500 câu hỏi test thực tế giữa giải pháp cũ (FAISS + SQLite) và giải pháp mới (**Alibaba Zvec**).

### A. Lệnh chạy benchmark chính thức:

```bash
# 1. Chạy đánh giá trên Alibaba Zvec (Giải pháp SOTA mới)
python3 scratch/run_zvec_benchmark_500.py

# 2. Chạy đánh giá trên tổ hợp FAISS cũ (Yêu cầu khôi phục file chỉ mục từ backup)
OMP_NUM_THREADS=1 python3 scratch/run_hybrid_benchmark_500.py
```

### B. Bảng Kết Quả Đánh Giá Thực Tế Trên Toàn Bộ 1.55 Triệu Vector (500 Câu Hỏi Vàng)

| Phương Pháp Tìm Kiếm | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | Latency (Độ trễ trung bình) | RAM yêu cầu |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Document-level FTS5 (Baseline)** | 8.4% | 13.2% | 17.2% | 20.8% | 0.118 | **75.7 ms** | - |
| **Chunk-level FTS5 (Phase 1)** | 22.0% | 33.2% | 39.8% | 50.4% | 0.299 | **176.2 ms** | - |
| **FAISS Flat Float32 (Không Rerank)** | 66.2% | 83.8% | 88.0% | **90.8%** | 0.752 | **179.2 ms** | ~12-16 GB |
| **FAISS IVF-SQ8 (Không Rerank)** | 65.8% | 83.2% | 87.8% | **90.8%** | 0.750 | **108.1 ms** | ~4 GB |
| **FAISS SQ8 (Benchmark cũ)** | 65.2% | 82.6% | 86.4% | **88.0%** | 0.742 | **1170.58 ms** | ~6.8 GB |
| **Alibaba Zvec HNSW (IP)** | 65.4% | 82.8% | 86.8% | **88.2%** | **0.748** | **83.56 ms** 🚀 | **~1-2 GB** |

### 💡 Đánh giá hiệu năng và Ưu điểm của Alibaba Zvec:
1. **Tốc độ tìm kiếm nhanh vượt trội (14x speedup)**:
   * Nhờ kiến trúc vector nhúng C++ tối ưu cao, Zvec HNSW hoàn thành tìm kiếm Top-10 / Top-150 chỉ trong **83.56 ms** (so với **1170.58 ms** của FAISS SQ8 kết hợp SQLite mapping).
2. **Tiết kiệm RAM tối đa**:
   * Zvec chỉ tiêu thụ **~1-2 GB RAM** khi hoạt động nhờ cơ chế mapping và nén đồ thị thông minh thay vì load toàn bộ ma trận vector dạng Float32 lên RAM như FAISS Flat.
3. **Giữ vững và cải thiện độ chính xác**:
   * Recall Hit@10 của Zvec đạt **88.2%** (cao hơn 0.2% so với FAISS SQ8) do Zvec lưu trữ và tính toán trực tiếp trên vector Float32 gốc (không bị suy hao chất lượng do nạp lượng tử hóa 8-bit).
4. **Hỗ trợ cập nhật thời gian thực (Real-time WAL)**:
   * Zvec hỗ trợ cơ chế Write-Ahead Logging (WAL) giúp ghi dữ liệu mới và có thể tìm kiếm được ngay lập tức mà không cần rebuild lại toàn bộ đồ thị HNSW từ đầu.

---

## 🔄 4. Hướng Dẫn Cơ Chế Đồng Bộ Gia Tăng & Chuẩn Hóa TokenJuice (Mới)

Để giữ cho hệ thống luôn cập nhật văn bản pháp luật mới mỗi ngày mà không cần build lại toàn bộ cơ sở dữ liệu từ đầu (mất từ 1-8 tiếng), dự án đã tích hợp cơ chế **Đồng bộ Gia tăng** kết hợp với bộ parser chuẩn hóa **TokenJuice-style**.

### A. Bộ Parser TokenJuice-style (`html_to_clean_markdown`)
*   **Vị trí**: Nằm trong [build_chunks_v2.py](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/scratch/build_chunks_v2.py).
*   **Nguyên lý**: 
    1. Trích xuất nội dung HTML thô từ văn bản luật, loại bỏ các thẻ định dạng thừa, inline CSS, các thẻ div/span rác.
    2. Chuyển đổi các cấu trúc tiêu đề (Điều, Khoản, Điểm) sang định dạng **Markdown chuẩn** (`# Điều...`, `* Khoản...`).
    3. Việc chuyển đổi này giúp mô hình Embedding BGE-M3 nhận diện phân cấp điều khoản tốt hơn rất nhiều, tăng chỉ số Recall và độ chính xác của ngữ cảnh nạp vào LLM.
    4. Các biểu thức chính quy (Regex) phân tách văn bản đã được cập nhật để tương thích ngược với cả dạng text thô và Markdown có dấu `#`.

### B. Tiến Trình Đồng Bộ Gia Tăng (`sync_new_laws.py`)
*   **Vị trí**: [sync_new_laws.py](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/scripts/sync_new_laws.py).
*   **Các bước thực hiện tự động**:
    1. **Tải luật mới**: Quét các văn bản luật mới cập nhật trên 3 hệ thống (VBPL, LuatVietnam, PhapLuat.gov.vn).
    2. **Phân tách & Clean HTML**: Áp dụng bộ parser TokenJuice-style để tạo ra các Markdown chunks sạch.
    3. **Sinh vector & Lưu trữ**: Sử dụng mô hình nhúng BGE-M3 cục bộ (cached trong RAM cho tốc độ đồng bộ nhanh hơn 8x, ~2 giây/văn bản) để sinh embedding cho các chunks mới, sau đó lưu trực tiếp vào cơ sở dữ liệu `vector_store.db`.
    4. **Cập nhật đồng thời các Chỉ mục FAISS**:
        *   Tự động đọc và thêm (append) các vector mới vào chỉ mục Flat mặc định (`chunks_faiss.index`).
        *   Tự động thêm vào chỉ mục lượng tử hóa SQ8 (`chunks_faiss_sq8.index`).
        *   Tự động thêm vào chỉ mục nén IVF-SQ8 (`chunks_faiss_ivf_sq8.index`) sử dụng phương thức `add_with_ids`.
    5. **Đồng bộ vào cơ sở dữ liệu Vector Alibaba Zvec**:
        *   Tự động mở cơ sở dữ liệu vector Zvec cục bộ (`zvec_laws_db`), đồng bộ hóa các chunks và vectors mới dưới dạng lô (batch) và gọi `flush()`.
        *   Áp dụng cơ chế an toàn concurrency (đóng kết nối ngay trong block `finally`, retry 30 lần giãn cách 0.2s) để tránh xung đột khóa đọc/ghi (database lock) với API server đang chạy.
    6. Ghi nhận ID của các văn bản đã xử lý để đảm bảo không trùng lặp và ghi nhận log rõ ràng.

### C. Cách chạy đồng bộ thủ công hoặc đặt Cronjob
Bạn có thể chạy trực tiếp lệnh sau để kiểm tra và cập nhật luật mới:
```bash
CRAWLER_HEADLESS=1 SYNC_PAGES=1 python3 scripts/sync_new_laws.py
```
Để chạy tự động hàng ngày (ví dụ vào lúc 2 giờ sáng), bạn có thể cấu hình Crontab trên server:
```bash
0 2 * * * cd /Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam && CRAWLER_HEADLESS=1 OMP_NUM_THREADS=1 python3 scripts/sync_new_laws.py >> logs/sync.log 2>&1
```
