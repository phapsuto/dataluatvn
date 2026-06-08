# 📋 Kế Hoạch Audit Mã Nguồn & Dọn Dẹp Toàn Diện Thư Mục Gốc (luatvietnam)
*Thời gian lập: 2026-06-08 20:41:00*

Kiến trúc thư mục gốc hiện tại đang chứa khá nhiều file log, file tạm và đặc biệt là các **script import/thiết lập một lần (one-off scripts)**. Để thư mục gốc chuẩn hóa và gọn gàng, chúng ta sẽ thực hiện dọn dẹp theo kế hoạch mới dưới đây.

Tác vụ này chạy độc lập và an toàn trong lúc tiến trình sinh vector (`task-671`) đang chạy ngầm.

---

## 🗑️ 1. Dọn Dẹp File Rác & File Tạm Ở Thư Mục Gốc

Các file dưới đây là file thô, file log hoặc cấu hình tạm thời, đề xuất **xóa vĩnh viễn**:

| Đường dẫn file | Loại file | Hành động | Lý do |
| :--- | :---: | :---: | :--- |
| `Bo_luat_To_tung_Dan_su_2015.doc` | Văn bản | **Xóa** | File tài liệu Word thô, đã được import toàn bộ vào CSDL chính. |
| `crawler_progress.json` | JSON | **Xóa** | Tiến trình cào tài liệu cũ, không còn giá trị. |
| `sync_progress.json` | JSON | **Xóa** | Tiến trình đồng bộ cũ. |
| `crontab` | Cấu hình | **Xóa** | File backup cấu hình cron cũ. |
| `real_card.html` | HTML | **Xóa** | Layout nháp hiển thị card cũ. |
| `debug_card.html` | HTML | **Xóa** | Layout nháp gỡ lỗi card cũ. |
| `fill_missing.log` | Log | **Xóa** | Log ghi nhận quá trình điền dữ liệu thiếu. |
| `sync.log` | Log | **Xóa** | Log ghi nhận quá trình đồng bộ cũ. |

---

## 📁 2. Di Chuyển Các Script Thiết Lập Một Lần Vào Thư Mục `scripts/`

Để thư mục gốc chỉ giữ lại các file khởi chạy chính (`server.py`, `requirements.txt`, `Dockerfile`...), toàn bộ các script import dữ liệu hoặc tối ưu DB sẽ được **di chuyển (move)** vào thư mục [scripts/](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/scripts):

| Tên file script gốc | Chức năng | Hành động |
| :--- | :--- | :--- |
| `import_anle.py` | Import dữ liệu Án lệ | Di chuyển sang `scripts/import_anle.py` |
| `import_phapdien.py` | Import dữ liệu Pháp điển | Di chuyển sang `scripts/import_phapdien.py` |
| `import_huggingface.py` | Tải dữ liệu từ HuggingFace | Di chuyển sang `scripts/import_huggingface.py` |
| `import_content_only.py` | Import nội dung thuần | Di chuyển sang `scripts/import_content_only.py` |
| `download_all_to_sqlite.py` | Download CSDL thô ban đầu | Di chuyển sang `scripts/download_all_to_sqlite.py` |
| `split_content_db.py` | Phân tách CSDL nội dung | Di chuyển sang `scripts/split_content_db.py` |
| `upgrade_db.py` | Nâng cấp cấu trúc DB | Di chuyển sang `scripts/upgrade_db.py` |
| `optimize_db.py` | Tối ưu chỉ mục và vacuum DB | Di chuyển sang `scripts/optimize_db.py` |
| `check_db.py` | Kiểm tra tính toàn vẹn của DB | Di chuyển sang `scripts/check_db.py` |
| `build_crosslinks.py` | Xây dựng liên kết chéo luật | Di chuyển sang `scripts/build_crosslinks.py` |
| `extract_modifications.py` | Trích xuất lịch sử sửa đổi | Di chuyển sang `scripts/extract_modifications.py` |
| `discover_api.py` | Khám phá API bên ngoài | Di chuyển sang `scripts/discover_api.py` |

*Lưu ý:* Sau khi di chuyển, thư mục gốc của dự án sẽ cực kỳ gọn gàng, chỉ còn:
*   Các thư mục cốt lõi: `app/`, `static/`, `data/`, `scripts/`, `scratch/`, `users_memory_faiss/`.
*   Các file cấu hình/khởi chạy: `server.py`, `status.py`, `mcp_server.py`, `progress_server.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`.
*   Các file tài liệu: `README.md`, `SERVER_INSTALL_GUIDE.md`, `nhatky.md`, `API_DOCS.md`, `KE_HOACH_XAY_DUNG_DATA_PHAP_LUAT.md`, `chongaogiac.md`, `huongdan.md`.
*   Các file DB chính: `vietnamese_legal_documents.db`, `vector_store.db`, `admin.db`, `user_session_memory.db`, `users_memory.db`, `chunks_faiss.index`.

---

## 🔍 3. Kế Hoạch Audit Mã Nguồn (Code Audit)

Chúng ta tiếp tục thực hiện audit code Python trong `app/` để:
1.  **Xóa bỏ các import không sử dụng** trong các file router và utility để tăng tốc độ load server.
2.  **Kiểm soát Exception**: Đảm bảo tất cả các API endpoint bọc trong `try-except` đầy đủ để tránh làm sập server khi có sự cố mạng.
3.  **Rà soát SQLite Connection**: Đảm bảo tất cả kết nối đến SQLite DB đều được đóng đúng cách thông qua `finally` hoặc context manager (`with`) để tránh lỗi `database is locked`.

---

## 🧪 4. Chạy API Health Check

Sau khi dọn dẹp và di chuyển code, chúng ta sẽ thực hiện kiểm tra tính sẵn sàng hoạt động của toàn bộ các API chính bằng công cụ kiểm thử nhanh.
