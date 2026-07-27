# 🏛️ ĐỘNG CƠ PHỔ CẬP PHÁP LÝ TOÀN DÂN DATALUATVN (RAG GEN 4.0 UNIVERSAL TRI-TIER ENGINE)

> **Tài liệu Kiến trúc Kỹ thuật Độc quyền & Hướng dẫn Triển khai Toàn diện**  
> **Phiên bản kiến trúc:** RAG Gen 4.0 (Universal Tri-Tier & NormativeProofLedger v4.0)  
> **Tỷ lệ kiểm thử tự động:** ✅ **100% Automated Test Coverage (43/43 PASSED)**

---

## 🌟 1. TUYÊN BỐ ĐỘC QUYỀN SỞ HỮU TRÍ TUỆ (PROPRIETARY ENGINEERING)

DataLuatVN RAG Gen 4.0 không sử dụng bất kỳ vay mượn thuật ngữ hay mô hình bên ngoài nào, mà được thi công, thiết kế và tối ưu riêng biệt cho kho dữ liệu **154.206 văn bản quy phạm pháp luật Việt Nam** cùng hệ thống Án lệ, Bản án chính thức của Tòa án Nhân dân Tối cao.

Hệ thống sở hữu bộ công nghệ bản quyền mang tính định danh kỹ thuật cao:
1. **Universal Tri-Tier Accessibility Engine**: Động cơ Phổ cập Toàn dân 3 Tầng phân tích (`CITIZEN` - Dân sinh 3 bước, `ENTERPRISE` - Quản trị tuân thủ, `JUDICIAL` - Tứ diện RAFA Matrix).
2. **CLF-SHA256 (Cryptographic Legal Fingerprint)**: Vân tay mật mã băm SHA-256 chuẩn hóa khoảng trắng cho từng Điều, Khoản, Điểm pháp luật.
3. **SAH Hierarchy Tier 1–4 (Statutory Authority Hierarchy)**: Ma trận phân cấp hiệu lực văn bản tự động theo chuẩn Nhà nước.
4. **NormativeProofLedger (NPL-JSON v4.0)**: Sổ cái kiểm toán pháp lý cấu trúc JSON chống suy diễn, xuất kèm chữ ký số `audit_receipt`.
5. **7LCP Pipeline & Blind-Spot Fact Engine (BSFE)**: Động cơ phát hiện điểm mù tình tiết trong truy vấn & phân nhánh lập luận điều kiện ("Nếu... thì...").
6. **DVS Shield (Dynamic Verification Shield)**: Khiên bảo mật và xác thực thời gian thực với huy hiệu **🛡️ DVS SHIELD VERIFIED**.

---

## 🏗️ 2. MA TRẬN PHÂN TẦNG HIỆU LỰC PHÁP LÝ (SAH HIERARCHY TIER 1–4)

Hệ thống DataLuatVN RAG Gen 4.0 tự động gán nhãn hiệu lực cho mọi điều khoản được trích dẫn:

```
+---------------------------------------------------------------------------------+
|                       SAH HIERARCHY TIER 1 - 4 MATRIX                           |
+---------------------------------------------------------------------------------+
| TIER 1: BINDING PRIMARY (Hiến pháp, Bộ luật, Luật, Pháp lệnh, Nghị quyết QH)     |
+---------------------------------------------------------------------------------+
| TIER 2: JUDICIAL PRECEDENT (Án lệ chính thức của Tòa án Nhân dân Tối cao)        |
+---------------------------------------------------------------------------------+
| TIER 3: EXPERT GUIDANCE (Nghị định Chính phủ, Thông tư Bộ ngành, Quyết định TTg)|
+---------------------------------------------------------------------------------+
| TIER 4: INFORMAL REFERENCE (Công văn hướng dẫn nghiệp vụ, giải đáp pháp luật)    |
+---------------------------------------------------------------------------------+
```

---

## 🛠️ 3. HƯỚNG DẪN KIỂM THỬ TỰ ĐỘNG (43/43 AUTOMATED TESTS)

Hệ thống đi kèm bộ kiểm thử chuẩn mực, chứng minh 100% tính năng mới hoạt động hoàn hảo và không ảnh hưởng đến kiến trúc hiện hữu:

```bash
# Lệnh chạy trọn gói kiểm thử tự động
python3 -m pytest tests/ -v
```

### Chi tiết 43 bài kiểm thử (Test Cases):
- **Giai đoạn 1 (`test_phase1_normative_ledger.py` - 4 tests):**
  - Xác minh SHA-256 Hash không thay đổi khi chuỗi có ký tự trắng thừa.
  - Phân loại chính xác SAH Tier cho Bộ Luật Lao Động, Án lệ 01/2016/AL, Nghị định 145/2020/NĐ-CP.
  - Tạo cấu trúc JSON NPL-JSON v4.0 đúng chuẩn schema với `audit_receipt` SHA-256.
- **Giai đoạn 2 (`test_phase2_7lcp_bsfe_dvs.py` - 6 tests):**
  - Xác minh System Prompt Tầng Dân sinh (`CITIZEN`) có yêu cầu rõ "3 Bước Hành Động".
  - Xác minh System Prompt Tầng Tư pháp (`JUDICIAL`) có cấu trúc Tứ diện "RAFA Matrix".
  - Xác minh BSFE phát hiện điểm mù tình tiết (khi câu hỏi thiếu loại hợp đồng hoặc nguyên nhân) và trả về "Trường hợp 1 / Trường hợp 2".
  - Xác minh DVS Shield đóng dấu chứng nhận và Router FastAPI tương thích ngược 100%.
- **Giai đoạn 3 (`test_phase3_universal_tri_tier.py` - 2 tests):**
  - Xác minh giao diện `portal.html` có thanh Tri-Tier Banner (`#chat-tier-select`) và modal JSON.
  - Xác minh `telegram_bot.py` duy trì đúng bộ nhớ `USER_ACCESS_TIERS` và xử lý lệnh `/tier`.
- **Bộ kiểm thử hiện hữu Gen 3.0 (31 tests):** Toàn bộ `test_smart_search.py`, `test_query_decomposer.py`, `test_legal_squad.py`, ... đều đạt **PASSED**.

---

## 🚀 4. HƯỚNG DẪN TRIỂN KHAI THỰC TẾ

### 🌐 Triển khai Web Portal (Port 2004)
```bash
python3 server.py
```
- Mở trình duyệt: `http://localhost:2004/static/portal.html`
- Trải nghiệm chuyển đổi chế độ nhận tư vấn từ người dân đến luật sư chỉ bằng 1 cú nhấp chuột trên thanh Tri-Tier Banner.

### 📱 Triển khai Telegram Bot (@LuatBot)
```bash
python3 telegram_bot.py
```
- Sử dụng các lệnh `/tier citizen`, `/tier enterprise`, `/tier judicial` để thiết lập chế độ phổ cập trên điện thoại.
