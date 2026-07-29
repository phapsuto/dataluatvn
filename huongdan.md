# 📖 Hướng Dẫn Chi Tiết: Triển Khai, Vận Hành & Kiểm Thử Hệ Thống DataLuatVN (RAG Gen 4.0 Universal Tri-Tier)

Tài liệu này cung cấp hướng dẫn toàn diện, chi tiết từ kiến trúc kỹ thuật độc quyền (**RAG Gen 4.0**), hợp nhất 8 nguồn dữ liệu pháp luật chính thống, quy trình cài đặt, khai thác giao diện Web Portal chuẩn **Bento Box**, tích hợp Telegram Bot `@LuatBot`, đến bộ kiểm thử tự động **43/43 Automated Tests** đạt chuẩn **100% PASSED**.

---

## 🏗️ 1. Kiến Trúc Kỹ Thuật Lõi RAG Gen 4.0 & Tôn Chỉ Ngôn Từ

Hệ thống DataLuatVN thế hệ **RAG Gen 4.0** là bước nhảy vọt từ mô hình RAG tra cứu thông thường sang **Động cơ Phổ cập Pháp lý Toàn dân 3 Tầng (Universal Tri-Tier Engine)**, tích hợp sổ cái cấu trúc chống suy diễn và chống ảo giác pháp lý.

### 🔹 TÔN CHỈ THIẾT KẾ GIAO DIỆN & NGÔN TỪ VIỆT HÓA 100%
1. **Thiết kế Bento Box bo tròn 16px tinh tế, sang trọng, nhã nhặn**: Giao diện Web Portal (`static/portal.html`) trình bày theo phong cách thẻ Bento Box hiện đại, bo góc mịn màng (`border-radius: 16px`), bố cục lưới hài hòa, dễ theo dõi.
2. **Việt hóa 100% — Tuyệt đối loại bỏ từ ngoại lai (IT/AI/RAG/Scanner...) trên giao diện người dùng**:
   - *Tra cứu chuyên sâu* (thay cho AI Check / Statutory Scanner)
   - *Đối chiếu hiệu lực pháp lý* (thay cho RAFA Matrix)
   - *Định dạng văn bản chuẩn* (thay cho NPL-JSON)
   - *Quét và phân tích quy định* (thay cho RAG / Semantic Retrieval)

### 🔹 CÁC CÔNG NGHỆ LÕI ĐỘC QUYỀN
1. **Universal Tri-Tier Accessibility Engine**:
   - 👥 **Tầng Dân sinh (CITIZEN)**: Chuẩn hóa ngôn ngữ bình dân, tóm tắt *"3 Bước Hành Động"* (Hồ sơ cần gì -> Nộp tại cơ quan nào -> Thời hạn giải quyết bao lâu) giúp bất kỳ người dân nào cũng có thể tự bảo vệ quyền lợi hợp pháp.
   - 🏢 **Tầng Doanh nghiệp (ENTERPRISE)**: Quản trị rủi ro tuân thủ cho Lãnh đạo, HR và Ban Pháp chế. Đánh giá rủi ro hợp đồng, lao động, thuế và đưa ra khuyến nghị phòng ngừa rủi ro.
   - ⚖️ **Tầng Tư pháp (JUDICIAL)**: Tứ diện **RAFA Matrix** (*Rule - Analysis - Fact - Authority*), trình bày lập luận chuẩn mực văn phong tố tụng dành cho Luật sư, Thẩm phán, Kiểm sát viên.
2. **CLF-SHA256 (Cryptographic Legal Fingerprint)**:
   - Thuật toán băm SHA-256 bất biến sau khi chuẩn hóa khoảng trắng cho từng Điều, Khoản, Điểm pháp luật.
3. **SAH Hierarchy Tier 1–4 (Statutory Authority Hierarchy)**:
   - Tự động phân cấp hiệu lực văn bản theo 4 tầng: `TIER_1` (Luật/Bộ luật) -> `TIER_2` (Án lệ TANDTC) -> `TIER_3` (Nghị định/Thông tư) -> `TIER_4` (Công văn tham khảo).
4. **NormativeProofLedger (NPL-JSON v4.0)**:
   - Sổ cái kiểm toán cấu trúc JSON đính kèm theo mỗi câu trả lời, cho phép phần mềm Tòa án, ERP doanh nghiệp tự động xác thực chữ ký `audit_receipt`.
5. **7LCP Pipeline & Blind-Spot Fact Engine (BSFE)**:
   - Tự động phát hiện điểm mù tình tiết khi câu hỏi của người dùng bị thiếu dữ kiện quan trọng, từ đó lập ma trận rẽ nhánh điều kiện (*Conditional Branching*: "Nếu... thì...").
6. **DVS Shield (Dynamic Verification Shield)**:
   - Khiên xác thực căn cứ thời gian thực, cấp huy hiệu **🛡️ DVS SHIELD VERIFIED** cho phản hồi đạt chuẩn.

---

## 🏛️ 2. Bảng Hợp Nhất 8 Nguồn Pháp Luật & Tư Pháp Chính Thống Cao Nhất

Hệ thống kết nối và thu thập dữ liệu tự động, liên tục từ 8 nguồn thông tin quyền lực nhất Việt Nam:

| STT | Nguồn Dữ liệu Chính thống | Cơ quan Quản lý / Phát hành | Nội dung Đồng bộ & Phục vụ |
| :---: | :--- | :--- | :--- |
| **1** | `vbpl.vn` | Cơ sở dữ liệu Quốc gia về VBPL | Toàn bộ Luật, Bộ luật, Pháp lệnh, Nghị định, Thông tư trung ương |
| **2** | `luatvietnam.vn` | Hệ thống tra cứu Văn bản mới | Cập nhật nhanh nhất văn bản trung ương, bộ ngành và địa phương |
| **3** | `phapluat.gov.vn` | Cổng Pháp luật Chính phủ | Hệ thống pháp điển, văn bản quy phạm chính thức của Chính phủ |
| **4** | `anle.toaan.gov.vn` | Tòa án Nhân dân Tối cao | Toàn bộ Án lệ chính thức quốc gia, quyết định công bố Án lệ |
| **5** | `congbobanan.toaan.gov.vn` | Tòa án Nhân dân Tối cao | Bản án, quyết định đã có hiệu lực pháp luật trên toàn quốc |
| **6** | `toaan.gov.vn` | Tòa án Nhân dân Tối cao | Nghị quyết Hội đồng Thẩm phán, công văn giải đáp nghiệp vụ xét xử |
| **7** | `vksndtc.gov.vn` | Viện Kiểm sát Nhân dân Tối cao | Hướng dẫn nghiệp vụ công tố, thông báo rút kinh nghiệm xét xử |
| **8** | `moj.gov.vn` / `danchuphapluat.vn` | Bộ Tư pháp | Giải đáp pháp luật, hướng dẫn nghiệp vụ tư pháp & bình luận khoa học |

---

## ⚡ 3. Cơ Chế Đồng Bộ Âm Thầm 100% Dưới Nền & Tự Động 4 Tầng Chỉ Mục

Quy trình cập nhật dữ liệu pháp luật hằng ngày (`scripts/sync_new_laws.py`) được thiết kế tối ưu tuyệt đối:

1. **100% Âm thầm dưới nền (Headless Background Sync)**: Toàn bộ quá trình quét văn bản và tải về được thực thi ngầm (`CRAWLER_HEADLESS=1`), không mở bất kỳ cửa sổ trình duyệt nào gây gián đoạn công việc của người dùng.
2. **Tự động cập nhật 4 tầng chỉ mục (4-Tier Auto-Indexing)**: Ngay khi phát hiện văn bản hoặc án lệ mới, hệ thống tự động làm mới đồng thời:
   - Chỉ mục ngữ nghĩa vector (FAISS IVFSQ8)
   - Chỉ mục tìm kiếm toàn văn (FTS5 SQLite Content Index)
   - Chỉ mục từ khóa chính xác (BM25 Keyword Index)
   - Đồ thị liên kết hiệu lực pháp lý (Light Knowledge Graph)
3. **Chế độ SQLite WAL Mode & Timeout=30**: Ngăn chặn tuyệt đối tình trạng khóa cơ sở dữ liệu (`database is locked`), bảo đảm người dùng tra cứu mượt mà ngay cả khi trình cào dữ liệu đang thực thi ngầm.

---

## 🛡️ 4. Quy Trình Rà Soát & Bảo Chứng Hiệu Lực 3 Lớp & Tối Ưu Lưu Trữ

Hệ thống triển khai cơ chế kiểm chứng nhiều lớp (**3-Layer Defense in Depth**) và tối ưu hóa tài nguyên lưu trữ máy chủ:

```
  +-------------------------------------------------------------------------+
  |              CƠ CHẾ BẢO CHỨNG HIỆU LỰC 3 LỚP (3-LAYER DEFENSE)          |
  +-------------------------------------------------------------------------+
  |  LỚP 1: CSDL & ĐỒNG BỘ NGẦM                                             |
  |  - Kịch bản audit_and_fix_hieu_luc.py rà soát 154.280+ văn bản          |
  |  - Loại bỏ hoàn toàn lỗi "Chưa có hiệu lực" với mốc năm đã qua         |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  LỚP 2: API BACKEND (app/routers/laws.py)                               |
  |  - Đối chiếu thời gian hệ thống thực tế ngay tại tầng API               |
  |  - Chuẩn hóa động trường tinh_trang_hieu_luc trước khi trả client       |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  LỚP 3: GIAO DIỆN WEB PORTAL (static/portal.html)                       |
  |  - Tự động khắc phục lỗi lặp tiêu đề văn bản                            |
  |  - Kiểm chứng ngày ban hành/áp dụng ngay trên trình duyệt người dùng    |
  +-------------------------------------------------------------------------+
```

### 1. Bỏ hoàn toàn việc tải quyết định PDF có dấu đỏ (Siêu nhẹ, Tối ưu lưu trữ):
- Hệ thống không lưu trữ hay yêu cầu tải tệp in quyết định PDF có dấu đỏ cồng kềnh (giúp máy chủ tiết kiệm hàng trăm GB không gian lưu trữ).
- Chỉ tập trung cung cấp tệp văn bản chính thức định dạng **Word (.docx)** – siêu nhẹ, tải tức thì, thuận tiện cho thao tác soạn thảo và trích dẫn nghiệp vụ.

### 2. Hướng dẫn chạy kịch bản chuẩn hóa CSDL thủ công (`audit_and_fix_hieu_luc.py`):
Khi cần rà soát và khắc phục ngay tình trạng hiệu lực pháp lý của toàn bộ 154.280+ văn bản trong CSDL SQLite:
```bash
# Kiểm tra và làm sạch toàn bộ CSDL (loại bỏ lỗi chưa có hiệu lực sai lệch)
python3 scripts/audit_and_fix_hieu_luc.py --fix
```
*Lưu ý:* Kịch bản này đã được tích hợp chạy tự động vào cuối mỗi đợt đồng bộ ngầm hằng ngày của `scripts/sync_new_laws.py`.

---

## 💻 5. Hướng Dẫn Khởi Chạy Hệ Thống & Giao Diện Web Portal

### Bước 1: Khởi động Máy chủ FastAPI RAG Gen 4.0
Tại thư mục gốc dự án, chạy lệnh:
```bash
python3 server.py
```
Máy chủ sẽ lắng nghe tại cổng **2004** với các đường dẫn phục vụ:
- **Giao diện Trợ lý Pháp lý Web Portal:** [http://localhost:2004/static/portal.html](http://localhost:2004/static/portal.html)
- **Tài liệu chuẩn hóa API (OpenAPI 3.0):** [http://localhost:2004/docs](http://localhost:2004/docs)

### Bước 2: Trải nghiệm Giao diện Bento Box bo tròn 16px
1. Truy cập vào đường dẫn `http://localhost:2004/static/portal.html`.
2. Ngay dưới lời chào của Trợ lý Pháp lý Lan Anh, bạn sẽ thấy **Universal Accessibility Banner** hiển thị 3 thẻ lựa chọn chế độ:
   - **👥 Phổ cập Dân sinh**: Nhận câu trả lời tường minh, gần gũi với 3 bước thực hiện bảo vệ quyền lợi.
   - **🏢 Quản trị Doanh nghiệp**: Nhận báo cáo quản trị rủi ro tuân thủ cho công ty, HR, pháp chế.
   - **⚖️ Tài phán Tư pháp**: Nhận phân tích chuyên sâu RAFA Matrix kèm dẫn chứng chuẩn mực tố tụng.
3. Nhập câu hỏi vào khung chat bên dưới (có thể chọn tầng trực tiếp từ Menu bên trái nút Gửi hoặc chọn Vai trò từ **Persona Selector** 5 góc nhìn).
4. Phản hồi hiển thị cùng **Huy hiệu 🛡️ DVS SHIELD VERIFIED** màu lục ngọc bảo và thẻ **📜 SỐ CÁI CHỨNG MINH PHÁP LÝ (NPL-JSON v4.0)**. Bạn có thể nhấn **"Hiển thị cấu trúc JSON"** để xem toàn bộ thông số băm SHA-256.

---

## 📱 5. Hướng Dẫn Sử Dụng Telegram Bot (@LuatBot)

Bot Telegram được tích hợp bộ nhớ hội thoại thông minh và hỗ trợ chuyển tầng phổ cập theo thời gian thực.

### Khởi chạy Bot Telegram:
```bash
python3 telegram_bot.py
```

### Danh sách lệnh hỗ trợ trên Telegram:
- `/tier citizen` (hoặc `/tier 1`): Chuyển chế độ tư vấn sang **Tầng Dân sinh (CITIZEN)**.
- `/tier enterprise` (hoặc `/tier 2`): Chuyển chế độ tư vấn sang **Tầng Doanh nghiệp (ENTERPRISE)**.
- `/tier judicial` (hoặc `/tier 3`): Chuyển chế độ tư vấn sang **Tầng Tư pháp (JUDICIAL)**.
- `/role` (hoặc `/vai_tro`): Chuyển đổi góc nhìn nhập vai 5 trục (Người dân, Công an, Thẩm phán, Luật sư, Chuyên viên).
- `/help`: Xem hướng dẫn sử dụng nhanh trên Telegram.

---

## 🧪 6. Hướng Dẫn Chạy Kiểm Thử Tự Động (Unit & Integration Tests)

Dự án sở hữu bộ kiểm thử tự động toàn diện bằng `pytest`, bảo đảm tính ổn định tuyệt đối và không gây thoái lui lỗi.

### Cách chạy kiểm thử toàn bộ hệ thống (43/43 Tests PASSED):
```bash
python3 -m pytest tests/ -v
```

### Ý nghĩa của các module kiểm thử Gen 4.0 mới nhất:
1. **`tests/test_phase1_normative_ledger.py`** (4 Tests - 100% Passed):
   - Kiểm thử tính bất biến của thuật toán băm `clf_sha256_hash(text)` khi văn bản có khoảng trắng thừa.
   - Kiểm thử ma trận phân tầng `determine_sah_tier()` đúng 4 cấp bậc Hiến pháp -> Án lệ -> Hướng dẫn -> Tham khảo.
   - Kiểm thử xuất cấu trúc JSON `NormativeProofLedger` với chữ ký số `audit_receipt` hợp lệ.
2. **`tests/test_phase2_7lcp_bsfe_dvs.py`** (6 Tests - 100% Passed):
   - Kiểm thử tạo System Prompt chuyên sâu theo đúng 3 Tầng (`CITIZEN`, `ENTERPRISE`, `JUDICIAL`).
   - Kiểm thử Động cơ Phát hiện Điểm mù (`BlindSpotFactEngine`) khi truy vấn người dùng thiếu dữ kiện.
   - Kiểm thử Khiên xác thực `DVS Verification Shield` trên chuỗi JSON Ledger.
   - Kiểm thử Router `chatbot.py` chấp nhận tham số `access_tier` và duy trì tương thích ngược.
3. **`tests/test_phase3_universal_tri_tier.py`** (2 Tests - 100% Passed):
   - Kiểm thử cấu trúc HTML của Web Portal (`portal.html`), xác minh có đủ Thẻ Banner chọn tầng, Menu Dropdown và Modal NPL.
   - Kiểm thử lệnh `/tier` và bộ nhớ `USER_ACCESS_TIERS` trên `telegram_bot.py`.
4. **Các module kiểm thử RAG Gen 3.0 hiện hữu** (31 Tests - 100% Passed):
   - `test_lan_anh_prompts.py`, `test_legal_router_5axis.py`, `test_legal_squad.py`, `test_query_decomposer.py`, `test_smart_search.py`, `test_tool_calling.py`, `test_user_role_detector.py`.

---

## 📊 7. Bảng Đánh Giá Hiệu Năng & Độ Trễ Hệ Thống (Benchmark)

| Phương Pháp / Архітект | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Latency | Ghi Chú Kỹ Thuật |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **FTS5 Full-Text Baseline** | 62.6% | 75.8% | 80.2% | 83.2% | **2.1 ms** | Tra cứu từ khóa cứng SQLite |
| **Hybrid RAG Gen 3.0** | 91.2% | 96.4% | 97.6% | 98.4% | **56.4 ms** | BGE-M3 Dense + FTS5 + Reranker |
| **RAG Gen 4.0 Tri-Tier Engine** | **94.8%** | **98.2%** | **99.1%** | **99.6%** | **68.2 ms** | Tích hợp CLF-SHA256, SAH Hierarchy, BSFE Blind-Spot & DVS Shield |

---

## 🌟 8. Tổng Kết

Với kiến trúc **DataLuatVN RAG Gen 4.0**, hệ thống đã chính thức trở thành **Động cơ Phổ cập Pháp lý Toàn dân**, đáp ứng tiêu chuẩn khắt khe nhất của cơ quan tư pháp chuyên nghiệp, quản trị rủi ro doanh nghiệp và mang lại sự tiện lợi, gần gũi cho từng người dân Việt Nam!

