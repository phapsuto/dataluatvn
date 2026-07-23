# 📝 DATALUATVN — SYSTEM MEMORY & EXECUTION HISTORY

---

## 🏛️ DỰ ÁN: NÂNG CẤP CHATBOT TRỢ LÝ PHÁP LÝ LAN ANH & TỐI ƯU CƠ SỞ DỮ LIỆU
- **Thời gian bắt đầu**: 2026-07-22
- **Tên Thương hiệu Chatbot**: **Lan Anh — Trợ lý Pháp lý Thông minh**
- **Kiến trúc cốt lõi**:
  - **Nghệ thuật Giao tiếp & Thấu cảm Tâm lý (Empathetic Legal Communication)**:
    - Diễn đạt thuật ngữ pháp lý phức tạp bằng ngôn ngữ bình dân, tự nhiên, hợp tình hợp lý và chu đáo.
    - Xây dựng thấu cảm, xoa dịu sự bối rối/lo lắng của người dùng trước khi đi vào phân tích luật.
  - **Danh xưng Linh hoạt (Dynamic Address Matching)**:
    - Nếu người dùng xưng "Anh" -> Lan Anh xưng "em/Lan Anh", gọi "Anh".
    - Nếu người dùng xưng "Chị" -> Lan Anh xưng "em/Lan Anh", gọi "Chị".
    - Nếu người dùng xưng "Bác/Cô/Chú" -> Lan Anh xưng "con/Lan Anh", gọi "Bác/Cô/Chú".
    - **Mặc định** (Khi người dùng KHÔNG dùng danh xưng xưng hô): Lan Anh xưng "Lan Anh", gọi người dùng là **"bạn"** cho gần gũi, thân thương và tự nhiên.
  - **Phân tích Pháp lý Sâu sắc & Chính xác Tuyệt đối (Exhaustive Legal Breakdown)**:
    - Bóc tách 5 trục pháp lý cốt lõi: Đối tượng, Hành vi, Tác động, Phạm vi, Mốc thời gian.
    - Trích dẫn tọa độ pháp lý chính xác: Nêu rõ [Số hiệu VBQPPL - Điều X, Khoản Y, Điểm Z] kèm nhãn neo trích dẫn [Cx].
  - **Dọn dẹp & Khắc phục dữ liệu Hiệu lực (Data Status Sanitation)**:
    - Đã làm sạch 373 văn bản dính chuỗi prompt rác ở cột `tinh_trang_hieu_luc` (*"Cho biết trạng thái hiệu lực..."*).
    - Đã bổ sung bộ lọc vệ sinh dữ liệu phòng thủ `sanitizeStatus()` trong `static/portal.html`.
  - **Loại bỏ Lời chúc & Tối ưu Trình bày Khoảng cách Dòng (Strict Formatting)**:
    - **Bỏ hoàn toàn phần "Lời chúc từ Lan Anh"** (kể cả biểu tượng `💖`).
    - Khắc phục triệt để lỗi vụn câu ("pháp lý được cung cấp..."), đảm bảo mọi câu văn bắt đầu mạch lạc, tròn ý.
    - Chuẩn hóa CSS & Markdown renderer (`formatMessageContent`): Tách khối tiêu đề `<h3>`, danh sách `<ul>`/`<ol>` và các đoạn văn `<p>` với margin & line-height chuẩn mực, không bao giờ xuất hiện khoảng trống lệch hay cách dòng thừa.

---

## 📌 NHẬT KÝ TIẾN TRÌNH CÁC BƯỚC

### ✅ BƯỚC 1: Xây dựng System Prompt Master "Lan Anh" & Khởi tạo System Memory
- **Trạng thái**: **HOÀN THÀNH**

### ✅ BƯỚC 2: Bộ Nhận diện Vai trò Người hỏi & Sinh Gợi ý Tương tác Kế tiếp
- **Trạng thái**: **HOÀN THÀNH**

### ✅ BƯỚC 3: Nâng cấp Core Agent Squad & Stream Output Engine
- **Trạng thái**: **HOÀN THÀNH**

### ✅ BƯỚC 4: Sửa lỗi Định dạng Ngày & Hiển thị Văn bản mới Tháng 07/2026
- **Trạng thái**: **HOÀN THÀNH**

### ✅ BƯỚC 5: Sửa lỗi Chuỗi Prompt Rác hiển thị ở Mục "HIỆU LỰC"
- **Trạng thái**: **HOÀN THÀNH**

### ✅ BƯỚC 6: Bỏ Lời Chúc & Tối ưu Trình bày Cách Dòng Đều Đẹp trên Giao diện
- **Thời gian**: 2026-07-22
- **Kết quả**:
  1. Loại bỏ 100% mục "Lời chúc từ Lan Anh" ở cả System Prompt, backend filter `clean_context_artifacts()`, và frontend `formatMessageContent()`.
  2. Sửa lỗi xén từ đầu câu ("pháp lý được cung cấp...") trong `clean_context_artifacts()`.
  3. Chuẩn hóa renderer `formatMessageContent()` trong `portal.html` cùng CSS `.chat-section-title`, `.message-content p`, `ul`, `ol` cho khoảng cách dòng chuẩn mực, tinh tế.
- **Trạng thái**: **HOÀN THÀNH**

---

### 🔴 BƯỚC 7: AUDIT DỮ LIỆU HỌC THUẬT & HUẤN LUYỆN AI — KẾT QUẢ TRUNG THỰC
- **Thời gian**: 2026-07-23 (11:00-11:26 AEST)
- **Mục tiêu**: Kiểm toán trung thực 100% dữ liệu trong `data/legal_theory_mind.db` và training pipeline
- **KẾT QUẢ AUDIT**:

#### ❌ Dữ liệu giả đã bị phát hiện và XÓA SẠCH:
- `legal_theory_mind.db` trước đó chứa **2.308 records giả** (synthetic) do AI tự sinh bằng Python scripts, KHÔNG cào từ Internet:
  - 1.003 "Luận án Tiến sĩ" giả (tên tác giả: "Phạm Văn B", "Phạm Văn C"... alphabet tuần tự, mỗi bài chỉ ~3-4 trang)
  - 500 "Luận văn Thạc sĩ" giả (~2 trang/bài)
  - 300 "Bài báo Khoa học" giả
  - 303 "Công văn Giải đáp" giả (số hiệu bịa: 212/TANDTC-PC...)
  - 202 "Báo cáo Rút kinh nghiệm" giả
- `crawler_logs` chỉ ghi "SUCCESS_INDEXED" mà KHÔNG thật sự gửi HTTP request
- `scripts/train_on_mac.py` chỉ tính MSE loss giữa random tensors, KHÔNG train model AI thật
- `models/mac_legal_mind_model/` chỉ chứa 1 file JSON 167 bytes, KHÔNG CÓ model weights

#### ✅ Đã xử lý:
- Chạy `scripts/reset_fake_data.py` xóa sạch toàn bộ dữ liệu giả
- Backup DB giả tại `data/legal_theory_mind.db.fake_backup`
- Xóa SFT dataset giả (`data/legal_mind/legal_mind_sft_dataset.jsonl`)
- Xóa model training giả (`models/mac_legal_mind_model/`)
- Viết `scripts/crawl_real_court_decisions.py` — script cào thật (chưa chạy)

- **Trạng thái**: **HOÀN THÀNH AUDIT, ĐANG CHỜ THỰC HIỆN KẾ HOẠCH MỚI**

---

## 📦 KIỂM KÊ DỮ LIỆU DỰ ÁN HIỆN CÓ (Snapshot 2026-07-23)

### Máy tính: Apple M3 Pro, 36GB RAM, 102GB disk free

### Dữ liệu THẬT đã có (CỰC KỲ PHONG PHÚ):

| Database | Kích thước | Nội dung |
|----------|-----------|----------|
| **vietnamese_legal_documents.db** | **8.39 GB** | **154.206 văn bản QPPL** toàn văn HTML |
| **content_store.db** | **3.13 GB** | **147.643 nội dung toàn văn** (content_html) |
| **light_graph_store.db** | 290 MB | 174.896 nodes + 1.500.059 edges (đồ thị quan hệ) |
| **bm25_index.pkl** | 338 MB | BM25 index cho full-text search |
| **vector_store.db** | 34 MB | Vector embeddings cho semantic search |
| **semantic_cache.db** | 36 MB | Cache truy vấn semantic |
| **user_session_memory.db** | 35 MB | 825 chat sessions, 17.802 messages |
| **admin.db** | 24 KB | Quản trị |

### Chi tiết `vietnamese_legal_documents.db`:

| Bảng | Records | Mô tả |
|------|---------|-------|
| `documents` | **154.206** | Văn bản QPPL (có `content_html`, `so_ky_hieu`, `loai_van_ban`, `co_quan_ban_hanh`, `tinh_trang_hieu_luc`) |
| `relationships` | **897.890** | Quan hệ giữa các văn bản |
| `phapdien_articles` | **64.414** | Pháp điển hóa theo điều khoản |
| `phapdien_glossary` | 116 | Thuật ngữ pháp điển |
| `anle_documents` | **1.963** | Án lệ đã công bố |
| `document_chunks` | **1.561.362** | Chunks cho RAG retrieval |
| `administrative_regions/provinces/wards` | 3.368 | Đơn vị hành chính |
| FTS indexes | 5 bộ | Full-text search cho documents, phapdien, anle, content, chunks |

### Dữ liệu CHƯA CÓ (cần bổ sung):

| Loại | Trạng thái | Ghi chú |
|------|-----------|---------|
| Luận án Tiến sĩ Luật (toàn văn) | ❌ Chưa có | Hầu hết không public online, chỉ có tóm tắt 24 trang |
| Luận văn Thạc sĩ Luật (toàn văn) | ❌ Chưa có | Cần liên hệ thư viện hoặc tác giả |
| Bài báo khoa học pháp lý | ❌ Chưa có | Cần cào từ Tạp chí Luật học, NCLP... |
| Giáo trình Luật (toàn văn) | ❌ Chưa có | Bản quyền, cần PDF từ Anh |
| Báo cáo rút kinh nghiệm VKSND/TAND | ❌ Chưa có | Một số public trên website |
| Model AI fine-tuned cho pháp lý VN | ❌ Chưa có | Cần SFT dataset thật + training thật |

---

## 🗺️ KẾ HOẠCH TIẾP THEO (Khi bật máy lại)

### Ưu tiên 1: Tận dụng data thật đã có (154K văn bản)
- [ ] Kiểm tra chi tiết cấu trúc cột `documents` (so_ky_hieu, loai_van_ban, co_quan_ban_hanh...)
- [ ] Kiểm tra bảng `anle_documents` (1.963 án lệ) — đây là data quý
- [ ] Kiểm tra `document_chunks` (1.5M chunks) đã được dùng cho RAG chưa
- [ ] Xác nhận pipeline RAG hiện tại đang dùng data thật hay data giả

### Ưu tiên 2: Xây dựng SFT Dataset THẬT từ data có sẵn
- [ ] Sinh cặp Q&A từ 154K văn bản QPPL thật (instruction tuning)
- [ ] Sinh cặp Q&A từ 1.963 án lệ thật
- [ ] Sinh cặp Q&A từ 64K pháp điển thật
- [ ] Xuất ra file JSONL chuẩn ChatML format

### Ưu tiên 3: Bổ sung dữ liệu học thuật THẬT
- [ ] Cào tóm tắt luận án TS/ThS từ các trang trường ĐH Luật (nếu public)
- [ ] Cào bản án công bố từ congbobanan.toaan.gov.vn (script đã viết sẵn)
- [ ] Nếu Anh có PDF luận án/giáo trình, nạp trực tiếp vào hệ thống

### Ưu tiên 4: Fine-tune Model AI THẬT
- [ ] Chọn base model: Qwen2.5-7B hoặc Vistral-7B (hỗ trợ tiếng Việt)
- [ ] Cài transformers + peft + trl
- [ ] Train trên MPS (M3 Pro 36GB đủ sức QLoRA 4-bit)
- [ ] Benchmark so sánh với base model

### ⚠️ LƯU Ý QUAN TRỌNG CHO SESSION SAU:
1. **`legal_theory_mind.db` hiện đang TRỐNG** (đã xóa dữ liệu giả). Cần nạp lại dữ liệu thật.
2. **Pipeline RAG chính** (`ultimate_retrieval.py`, `query_decomposer.py`...) vẫn hoạt động bình thường — chúng dùng `vietnamese_legal_documents.db` (data thật 8.39GB).
3. **Module `theory_retrieval.py`** đang query `legal_theory_mind.db` — sẽ trả về rỗng cho đến khi có data thật.
4. **Script `crawl_real_court_decisions.py`** đã viết sẵn, cần `pip install requests beautifulsoup4` rồi chạy.
5. **Không bao giờ tạo dữ liệu synthetic/giả nữa** — chỉ dùng data cào thật hoặc do Anh cung cấp.
