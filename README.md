# LuatBot API - Trợ lý Pháp lý AI Việt Nam (RAG 7 Tầng)

LuatBot là hệ thống Trợ lý Pháp lý Trí tuệ Nhân tạo tiên tiến nhất dành riêng cho Luật pháp Việt Nam. Hệ thống sử dụng kiến trúc **RAG (Retrieval-Augmented Generation) 7 Tầng SOTA** để đảm bảo độ chính xác tuyệt đối, giảm thiểu ảo giác (hallucination) và trích dẫn chuẩn xác từng Điều khoản.

## 🌟 Tính năng nổi bật

1. **Kiến trúc RAG 7 Tầng Độc quyền**:
   - Tầng 1: **Semantic Router (GPU Local)** phân tích ý định, bóc tách thực thể pháp lý.
   - Tầng 2: **Long-term User Memory** cá nhân hóa câu trả lời dựa theo hồ sơ người dùng.
   - Tầng 3: **Hybrid Retrieval** kết hợp Sparse (BM25) và Dense (FAISS) trên hơn 153.000 văn bản.
   - Tầng 4: **Cross-Encoder Reranking** loại bỏ nhiễu, xếp hạng lại kết quả chính xác nhất.
   - Tầng 5: **Adaptive FLARE (Forward-Looking Active Retrieval Generation)** chủ động tra cứu bù đắp thông tin nếu LLM thiếu tự tin.
   - Tầng 6: **P-Cite Citation Lock** ép LLM trích dẫn nguyên văn, chống "chế" luật.
   - Tầng 7: **Semantic Cache** (RAG Gen 3) phản hồi tức thì dưới 1s cho các câu hỏi trùng lặp.

2. **Đa nền tảng (Omni-channel)**:
   - Cung cấp RESTful API (FastAPI) tốc độ cao.
   - Tích hợp trực tiếp **Telegram Bot** (`telegram_bot.py`) để tư vấn pháp luật tức thời.

3. **Tối ưu hóa Tài nguyên (Resource Efficiency)**:
   - Chạy mượt mà trên máy chủ VPS RAM 10GB với cơ chế Auto-Fallback sang SQLite Memory khi thiếu RAM đồ họa.
   - Lọc nhiễu thông minh, xử lý mượt mà hơn 153,000 văn bản pháp luật, bản án và án lệ.

## 🏗️ Kiến trúc Hệ thống

- **Backend**: FastAPI, Uvicorn
- **Vector Database**: FAISS (Local) kết hợp SQLite
- **Mô hình Embedding**: bkai-foundation-models/vietnamese-bi-encoder
- **Mô hình LLM Core**: Hỗ trợ linh hoạt FPT Cloud (Qwen), Google Gemini, OpenAI
- **Process Manager**: PM2

## 🚀 Hướng dẫn Cài đặt & Khởi chạy

### 1. Yêu cầu Hệ thống
- HĐH: Ubuntu/Linux hoặc macOS
- Python: 3.11+
- RAM: Tối thiểu 10GB (Khuyến nghị bật Swap nếu dùng chung nhiều services)

### 2. Cài đặt Môi trường
```bash
# Clone source code
git clone https://github.com/phapsuto/dataluatvn.git
cd dataluatvn

# Tạo môi trường ảo
python3 -m venv venv
source venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt
```

### 3. Cấu hình Biến Môi trường
Tạo file `.env` tại thư mục gốc và điền các API Keys:
```env
# FPT Cloud API
FPT_CLOUD_CLIENT_ID=your_fpt_client_id
FPT_CLOUD_CLIENT_SECRET=your_fpt_client_secret

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# (Optional) Các mô hình dự phòng
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
```

### 4. Khởi chạy Hệ thống với PM2 (Dành cho Server / VPS)
Để đảm bảo hệ thống chạy ngầm và tự động khởi động lại, sử dụng `pm2`:

```bash
# 1. Chạy API Server (FastAPI)
pm2 start ./venv/bin/uvicorn --name api_server --interpreter ./venv/bin/python -- server:app --host 127.0.0.1 --port 2004 --workers 1

# 2. Chạy Telegram Bot
pm2 start telegram_bot.py --interpreter ./venv/bin/python --name telegram_bot

# 3. Lưu cấu hình PM2
pm2 save
```

## 🛠️ Cấu trúc Source Code

- `server.py`: Điểm khởi chạy của FastAPI Server.
- `telegram_bot.py`: Source code của Bot Telegram tích hợp LuatBot API.
- `app/routers/`: Chứa các endpoint API (Chatbot, Tìm kiếm Luật, Phân tích Án lệ...).
- `app/utils/`: Chứa toàn bộ "trái tim" của hệ thống RAG (Retrieval, Reranker, FLARE, Memory, Smart Router...).
- `users_memory.db`: Database lưu trữ lịch sử hội thoại cá nhân hóa của người dùng (Fallback mode).

## 🛡️ Giấy phép (License)
Dự án được phát triển và sở hữu độc quyền bởi **Pháp Sư Tồ (Phapsuto)**. Vui lòng không sao chép thương mại khi chưa có sự đồng ý.
