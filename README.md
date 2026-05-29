# 🚀 dataluatvn — Máy Chủ Dữ Liệu Pháp Luật Việt Nam (API & Data Engine)

> REST API hiệu năng cao và Trình cập nhật dữ liệu tự động cho hơn **153.420 văn bản pháp luật Việt Nam** cùng **897.890 mối liên kết pháp lý**. Giải pháp tối ưu nhất để xây dựng Chatbot RAG (AI) và Website tra cứu luật chuyên nghiệp.

---

## 🌟 Tính Năng Nổi Bật

1.  **Dữ liệu 100% Toàn Diện:** Tích hợp đầy đủ văn bản pháp luật Việt Nam (Luật, Nghị định, Thông tư, Án lệ...) từ trung ương đến địa phương từ trước đến nay.
2.  **Cập nhật tự động (Data Engine):** Quy trình chạy ngầm hàng đêm tự động đồng bộ hóa các văn bản mới ban hành từ cổng thông tin gốc của Chính phủ (`vbpl.vn`).
3.  **REST API Sẵn Sàng (FastAPI):** Cung cấp các API tìm kiếm siêu tốc, lấy toàn văn chi tiết dạng HTML, thống kê dữ liệu và thiết lập sẵn tài liệu tương tác tự động tại `/docs` (Swagger UI).
4.  **Hỗ trợ RAG & AI Chatbot:** Cấu trúc dữ liệu tối ưu hóa cho việc cắt nhỏ điều khoản (Semantic Chunking) và tạo Vector DB phục vụ chatbot LLM.
5.  **CORS Mở Rộng (`*`):** Cho phép kết nối trực tiếp và dễ dàng từ bất kỳ ứng dụng Frontend nào (React, Vue, Next.js...) chạy trên cổng bất kỳ.

---

## 📂 Cấu Trúc Dự Án

*   `server.py`: Mã nguồn máy chủ REST API viết bằng FastAPI, phục vụ truy vấn dữ liệu.
*   `sync_new_laws.py`: Tiến trình chạy ngầm định kỳ hàng ngày để quét và tải các văn bản luật mới ban hành.
*   `download_all_to_sqlite.py`: Script dùng để tải bộ dữ liệu ban đầu (~153.420 văn bản) từ HuggingFace và dựng tệp cơ sở dữ liệu SQLite `vietnamese_legal_documents.db` (3.2 GB).
*   `huongdan.md`: Tài liệu hướng dẫn lập trình kết nối API & Database (dành cho lập trình viên Backend/Frontend).
*   `KE_HOACH_XAY_DUNG_DATA_PHAP_LUAT.md`: Bản quy hoạch kiến trúc dữ liệu và lộ trình xây dựng hệ thống chatbot AI.

---

## 🛠️ Hướng Dẫn Vận Hành & Triển Khai Trên Máy Chủ (Server/VPS)

Dưới đây là các bước chi tiết để thiết lập và chạy máy chủ dữ liệu này trên Cloud VPS (Ubuntu/Linux hoặc Windows Server).

### Bước 1: Chuẩn bị Môi trường
Đảm bảo máy chủ của bạn đã cài đặt **Python 3.9+** và **pip**.

Cài đặt các thư viện cần thiết bằng câu lệnh:
```bash
pip install fastapi uvicorn requests beautifulsoup4 pyarrow huggingface_hub
```

### Bước 2: Khởi tạo Cơ sở dữ liệu gốc (Base Database)
Do tệp database có dung lượng lớn (3.2 GB), chúng ta không commit trực tiếp lên Git để tránh quá tải. Hãy chạy script khởi tạo sau trên máy chủ để tự động tải và dựng database:

```bash
python3 download_all_to_sqlite.py
```
> Tiến trình này sẽ tự động tải các tệp Parquet nén tốc độ cao từ HuggingFace và lập chỉ mục SQLite. Quá trình mất khoảng vài phút và sẽ sinh ra tệp dữ liệu duy nhất: `vietnamese_legal_documents.db`.

### Bước 3: Khởi chạy Máy chủ REST API
Chạy máy chủ API bằng Uvicorn trên cổng `8080` (hoặc cổng bất kỳ tùy chọn):

```bash
# Chạy thủ công
python3 server.py

# Hoặc chạy ngầm vĩnh viễn trên Linux bằng PM2
pm2 start "python3 server.py" --name "dataluat-api"
```

*   **Địa chỉ truy cập API:** `http://<IP-MÁY-CHỦ>:8080`
*   **Trang tài liệu tương tác tự động:** `http://<IP-MÁY-CHỦ>:8080/docs`

### Bước 4: Thiết lập lịch trình tự động cập nhật hàng đêm (Cron Job)
Để hệ thống tự cập nhật các luật mới ban hành mỗi đêm lúc **00:00**, hãy thiết lập một Cron Job trên máy chủ Linux:

1.  Mở bảng Cron Job:
    ```bash
    crontab -e
    ```
2.  Thêm dòng sau ở cuối tệp tin và lưu lại:
    ```bash
    0 0 * * * cd /path/to/dataluatvn && /usr/bin/python3 sync_new_laws.py >> sync.log 2>&1
    ```

---

## 🐳 Triển Khai Bằng Docker (Khuyên Dùng Cho Production)

Nếu bạn muốn chạy dự án này trên môi trường container hóa Docker cực kỳ hiện đại:

1.  **Dựng Docker Image:**
    ```bash
    docker build -t dataluat-engine .
    ```
2.  **Khởi chạy Container:**
    ```bash
    docker run -d -p 8080:8080 --name dataluat-container -v $(pwd):/app dataluat-engine
    ```

---

## 📞 Liên Hệ & Hỗ Trợ
Dự án được duy trì và phát triển bởi **Pháp sư Tô** và đội ngũ phát triển. Vui lòng gửi Pull Request hoặc tạo Issue nếu bạn muốn đóng góp cho kho dữ liệu pháp luật Việt Nam ngày càng hoàn thiện!
