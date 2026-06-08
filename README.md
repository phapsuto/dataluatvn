# 🚀 dataluatvn — Hệ Thống Tra Cứu Dữ Liệu Pháp Luật & AI Chatbot RAG 7 Tầng Việt Nam

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.0+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg?style=flat&logo=SQLite&logoColor=white)](https://www.sqlite.org/)
[![FAISS](https://img.shields.io/badge/FAISS-FlatIP%20%7C%20IDMap-FF6F00.svg)](https://github.com/facebookresearch/faiss)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**dataluatvn** là giải pháp REST API hiệu năng cao và AI Chatbot RAG (Retrieval-Augmented Generation) chuyên sâu dành cho hệ thống pháp luật Việt Nam. Hệ thống quản lý và khai thác kho dữ liệu khổng lồ gồm hơn **153.420 văn bản pháp luật quy phạm**, **897.890 mối liên kết pháp lý chéo**, toàn bộ hệ thống **Pháp Điển Việt Nam**, cùng hệ thống **Án Lệ và Bản Án** chính thức.

Dự án được thiết kế tối ưu hóa tài nguyên phần cứng cực độ (tách kiến trúc cơ sở dữ liệu), cho phép chạy mượt mà trên môi trường máy chủ cấu hình thấp (RAM chỉ từ 50-80 MB cho API server) trong khi vẫn đảm bảo độ chính xác vượt trội nhờ hệ thống AI Chatbot RAG 7 tầng chống ảo giác thông tin tuyệt đối.

---

## 🌟 Tính Năng Nổi Bật

*   🔍 **Tìm Kiếm Lai (Hybrid Search):** Kết hợp Full-Text Search (FTS5 BM25) cho các truy vấn chính xác theo số hiệu/từ khóa cứng và Dense Vector Search (FAISS) cho các truy vấn ngữ nghĩa tự nhiên.
*   🤖 **AI Chatbot RAG 7 Tầng (LuatBot Ultimate):** Kiến trúc xử lý câu hỏi pháp luật phức tạp qua 7 bước độc lập từ định tuyến ý định, nạp trí nhớ dài hạn, tìm kiếm đồ thị mở rộng, rerank ứng viên, sinh câu trả lời tự kiểm duyệt FLARE, đến khóa nguồn trích dẫn P-Cite.
*   🌳 **Đồ Thị Liên Kết Pháp Lý (Lineage Tree):** Dựng cây phả hệ nguồn luật hướng dọc (căn cứ ban hành, hướng dẫn thi hành) và hướng ngang (sửa đổi, bổ sung, thay thế) trực quan cao.
*   ⚖️ **Đối Soát Tranh Chấp Điều 156:** Thuật toán tự động đối chiếu các quy định pháp luật chồng chéo dựa trên quy tắc ưu tiên luật cấp trên (Rank hiệu lực) và ưu tiên luật mới ban hành (Khoản 2 Điều 156 Luật ban hành VBQPPL 2015).
*   ⚡ **Kiến Trúc Tách DB (Split Database):** Tách riêng phần dữ liệu HTML toàn văn siêu nặng ra khỏi DB tìm kiếm chính giúp giảm tải RAM hoạt động từ ~3 GB xuống chỉ còn 50-80 MB.
*   🤖 **Hỗ Trợ MCP Server (Model Context Protocol):** Cung cấp cổng kết nối STDIO trực tiếp để tích hợp cơ sở dữ liệu pháp luật với các AI clients như Cursor, Claude Desktop giúp hỗ trợ lập trình viên/luật sư tra cứu nhanh.

---

## 🤖 Kiến Trúc AI Chatbot RAG 7 Tầng (LuatBot Ultimate)

Để giải quyết triệt theo vấn đề ảo giác thông tin (hallucination) - điểm yếu chí mạng của LLM khi trả lời câu hỏi pháp luật đòi hỏi độ chính xác tuyệt đối, **dataluatvn** triển khai quy trình RAG 7 Tầng nghiêm ngặt:

```text
[Người Dùng Gửi Câu Hỏi]
         ↓
  ┌──────────────┐
  │   TẦNG 1     │ → [Semantic Router] Định tuyến ý định (Pháp luật / Chitchat / Out of Scope)
  └──────────────┘
         ↓ (Nếu thuộc phạm vi pháp luật)
  ┌──────────────┐
  │   TẦNG 2     │ → [Mem0 Long-Term Memory] Gợi nhớ thông tin cá nhân & lịch sử ngữ cảnh
  └──────────────┘
         ↓
  ┌──────────────┐
  │   TẦNG 3     │ → [HippoRAG Hybrid Search] FTS5 BM25 + FAISS Vector + Graph Expansion
  └──────────────┘
         ↓
  ┌──────────────┐
  │   TẦNG 4     │ → [Cohere Rerank API] Sắp xếp lại top ứng viên liên quan nhất
  └──────────────┘
         ↓
  ┌──────────────┐
  │   TẦNG 5     │ → [FLARE Active Generation] Sinh câu trả lời & Tự động phát hiện thiếu thông tin
  └──────────────┘     để truy vấn ngược lại (Query Expansion) nếu độ tin cậy thấp.
         ↓
  ┌──────────────┐
  │   TẦNG 6     │ → [P-Cite Citation Lock] Tự động khóa chặt mã trích dẫn, đối soát text thực tế
  └──────────────┘
         ↓
  ┌──────────────┐
  │   TẦNG 7     │ → [LiteLLM Gateway] Quản lý đa mô hình (Gemini/Claude), tự động fallback khi lỗi
  └──────────────┘
         ↓
[LuatBot Trả Lời Trích Dẫn Chuẩn Xác 100%]
```

### Chi tiết hoạt động từng tầng:
1.  **Tầng 1: Semantic Intent Router:** Sử dụng mô hình phân loại nhẹ chạy cục bộ để phân tích ý định. Nếu là hỏi đáp thông thường (Chitchat), server trả lời nhanh. Nếu nằm ngoài phạm vi pháp luật Việt Nam (Out of Scope), server từ chối lịch sự để tiết kiệm context. Nếu là câu hỏi pháp luật, hệ thống trích xuất bộ lọc loại văn bản phù hợp.
2.  **Tầng 2: Long-Term Memory (Mem0):** Quản lý hồ sơ người dùng lưu trong `user_session_memory.db`. Nhớ các thông tin người dùng đã chia sẻ trước đó (VD: doanh nghiệp của họ ở tỉnh nào, lĩnh vực hoạt động) để tự động áp dụng bộ lọc luật địa phương hoặc ngành nghề phù hợp.
3.  **Tầng 3: HippoRAG Hybrid Search:** Tìm kiếm song song:
    *   *BM25 FTS5:* Khớp từ khóa thô, số hiệu văn bản chính xác.
    *   *FAISS Dense Vector:* So khớp ý nghĩa ngữ nghĩa của câu hỏi với 1.55 triệu chunks bằng mô hình `vietnamese-bi-encoder`.
    *   *Graph Expansion:* Từ các văn bản tìm được, hệ thống tự động đi theo các liên kết pháp lý để lấy thêm các văn bản sửa đổi/hướng dẫn thi hành của nó, tạo thành một mạng lưới thông tin toàn diện.
4.  **Tầng 4: Cohere Rerank:** Gửi các chunk ứng viên qua Cohere Rerank API (hoặc local cosine-similarity) để tính toán điểm số phù hợp thực tế nhất, giữ lại top 5 chunk chất lượng cao.
5.  **Tầng 5: FLARE (Forward-Looking Active Retrieval):** Trong lúc LLM đang sinh câu trả lời, nếu phát hiện một câu/cụm từ có xác suất tin cậy thấp (low confidence tokens), hệ thống sẽ tạm dừng sinh, lấy cụm từ đó làm từ khóa truy vấn ngược lại cơ sở dữ liệu để tìm thông tin chính xác bổ sung, rồi mới tiếp tục sinh tiếp.
6.  **Tầng 6: P-Cite Citation Lock:** Cơ chế khóa trích dẫn. Hệ thống đối soát trực tiếp câu trả lời của LLM với dữ liệu thô trong cơ sở dữ liệu. Nếu phát hiện số hiệu văn bản hoặc điều luật bị LLM "bịa ra" không tồn tại trong DB, hệ thống sẽ tự động gỡ bỏ hoặc hiệu chỉnh lại chính xác.
7.  **Tầng 7: LiteLLM Gateway:** Đầu mối kết nối với các API LLM. Hỗ trợ dự phòng tự động (Ví dụ: Nếu Gemini API bị rate limit hoặc lỗi kết nối, hệ thống tự động chuyển hướng sang Claude hoặc GPT-4o). Có thể đổi mô hình runtime qua API nhanh chóng.

---

## 📂 Cấu Trúc Dự Án

```
luatvietnam/
├── server.py                      # FastAPI API server - Điểm khởi chạy chính
├── mcp_server.py                  # Cổng kết nối MCP Server cho Claude/Cursor
├── status.py                      # Công cụ giám sát tiến độ sinh vector & sức khỏe DB
├── Dockerfile                     # Cấu hình Docker build
├── docker-compose.yml             # Cấu hình khởi chạy nhanh bằng Docker Compose
├── requirements.txt               # Danh sách thư viện Python cơ bản
├── app/                           # Mã nguồn lõi của ứng dụng FastAPI
│   ├── config.py                  # Cấu hình hệ thống & API Keys
│   ├── database.py                # Kết nối & tối ưu hóa cơ sở dữ liệu SQLite
│   ├── dependencies.py            # Middleware xác thực (JWT & API Keys)
│   ├── hybrid_search.py           # Bộ tìm kiếm lai BM25 + FTS5
│   ├── routers/                   # Các router API theo phân hệ
│   │   ├── chatbot.py             # Router Chatbot AI RAG 7 Tầng
│   │   ├── laws.py                # Router văn bản pháp luật, Smart Search
│   │   ├── anle.py                # Router Án Lệ & Bản Án
│   │   ├── phapdien.py            # Router Pháp Điển
│   │   ├── lineage.py             # Router đồ thị & liên kết nguồn luật
│   │   ├── assistant_memory.py    # Router quản lý bộ nhớ người dùng
│   │   ├── admin_crud.py          # Router các thao tác CRUD dữ liệu của Admin
│   │   └── dashboard_api.py       # Router cung cấp dữ liệu biểu đồ phân tích
│   ├── utils/                     # Tiện ích bổ trợ nghiệp vụ
│   │   ├── llm_gateway.py         # Cổng kết nối đa LLM (LiteLLM)
│   │   ├── legal_router.py        # Semantic Router phân loại câu hỏi
│   │   ├── ultimate_retrieval.py  # Hệ thống truy xuất lai (BM25 + FAISS + Graph)
│   │   ├── flare_retrieval.py     # Triển khai thuật toán FLARE
│   │   └── user_memory.py         # Triển khai bộ nhớ Mem0 lưu trữ SQLite local
│   └── schemas/                   # Pydantic models đặc tả dữ liệu vào/ra
├── scripts/                       # Các kịch bản cài đặt, import & tối ưu hóa DB
│   ├── download_all_to_sqlite.py  # Tải 3 CSDL gốc từ HuggingFace về máy
│   ├── import_anle.py             # Import dữ liệu Án lệ vào DB chính
│   ├── import_phapdien.py         # Import dữ liệu Pháp điển vào DB chính
│   ├── split_content_db.py        # Tách nội dung HTML toàn văn sang DB riêng
│   ├── optimize_db.py             # Tạo chỉ mục tìm kiếm FTS5 & VACUUM tối ưu hóa
│   ├── upgrade_db.py              # Cập nhật schema & cờ nội dung cho các bảng
│   ├── build_crosslinks.py        # Xây dựng mối liên kết chéo giữa các văn bản
│   ├── build_vector_index.py      # Sinh embeddings & xây dựng chỉ mục FAISS
│   └── sync_new_laws.py           # Đồng bộ tự động văn bản pháp luật mới hàng ngày
└── scratch/                       # Thư mục nháp thử nghiệm & benchmark
    ├── build_chunks_v2.py         # Chunk tài liệu phục vụ sinh vector
    ├── test_api_endpoints.py      # Script test sức khỏe 11 endpoints API tự động
    └── test_luatbot_ultimate.py   # Script kiểm thử chất lượng RAG Chatbot
```

### 📦 Kiến Trúc Database Sau Khi Tối Ưu RAM
Để tránh việc SQLite tải dữ liệu HTML thô cực nặng vào bộ nhớ RAM khi thực hiện tìm kiếm danh sách hoặc rà soát liên kết, hệ thống thực hiện tách cơ sở dữ liệu làm 5 tệp chuyên biệt:

1.  `vietnamese_legal_documents.db` (~585 MB): Lưu toàn bộ metadata của 153k văn bản, 897k liên kết, chỉ mục FTS5, mục lục Pháp Điển, Án Lệ. Chạy cực nhanh, RAM load tối thiểu.
2.  `content_store.db` (~3.1 GB): Chỉ lưu trường `content_html` (nội dung toàn văn) của các văn bản. Chỉ được truy vấn theo ID khi người dùng click xem chi tiết.
3.  `vector_store.db` (~3.3 GB): Lưu trữ cache các vector embedding (768 chiều) của 1.55 triệu chunks văn bản, giúp không phải sinh lại embedding khi build lại FAISS index.
4.  `user_session_memory.db` (~290 KB): Lưu trữ vết hội thoại và bộ nhớ ngữ cảnh người dùng của Mem0.
5.  `admin.db` (~24 KB): Lưu trữ thông tin đăng nhập admin và API Keys.

---

## 🛠️ Hướng Dẫn Cài Đặt Từ Đầu (Step-by-Step)

Khi bạn clone dự án này về từ GitHub, bạn sẽ không có sẵn các tệp cơ sở dữ liệu SQLite lớn (`.db`), tệp chỉ mục FAISS (`.index`) hay file chỉ mục BM25 (`.pkl`) vì chúng quá nặng và đã bị loại khỏi Git qua cấu hình `.gitignore`. 

Bạn cần thực hiện tuần tự các bước dưới đây để tải dữ liệu, thiết lập môi trường và tự động xây dựng lại toàn bộ hệ thống từ đầu.

### 📋 Yêu Cầu Hệ Thống
*   **Hệ điều hành:** macOS, Linux (Ubuntu/Debian) hoặc Windows (qua WSL2).
*   **Python:** Phiên bản 3.9 trở lên.
*   **Phần cứng khuyến nghị:**
    *   RAM: Tối thiểu 16 GB (Khuyên dùng để chạy mượt mà bước sinh vector).
    *   Ổ cứng: Còn trống tối thiểu 50 GB SSD (Tốc độ đọc ghi của SSD ảnh hưởng trực tiếp đến hiệu năng SQLite và FAISS).
    *   GPU (Tùy chọn): CUDA-supported NVIDIA GPU hoặc Apple Silicon (M1/M2/M3) giúp tăng tốc độ sinh vector lên gấp 10-20 lần so với CPU.

---

### 💻 Các Bước Cài Đặt Chi Tiết

#### Bước 1: Clone dự án và truy cập thư mục
```bash
git clone <URL_REPOSITOY_CỦA_BẠN>
cd luatvietnam
```

#### Bước 2: Cài đặt các thư viện Python cần thiết
Chúng ta cần cài đặt các thư viện cho API Server và các thư viện học máy nặng để sinh Vector + FAISS Index:
```bash
# Cập nhật pip lên bản mới nhất
pip install --upgrade pip

# Cài đặt các thư viện cơ bản
pip install -r requirements.txt

# Cài đặt các thư viện phục vụ AI Chatbot & Vector Index
pip install torch torchvision torchaudio
pip install sentence-transformers faiss-cpu
pip install beautifulsoup4 langchain-text-splitters cohere litellm mem0-ai
```
> *Lưu ý về FAISS:* Nếu máy chủ của bạn có card đồ họa NVIDIA CUDA, hãy cài đặt `pip install faiss-gpu` thay vì `faiss-cpu` để tăng tốc độ tối đa.

#### Bước 3: Tải cơ sở dữ liệu gốc từ HuggingFace
Tập lệnh này sẽ tự động tải các file database SQLite chứa dữ liệu pháp luật Việt Nam thô đã được Pháp sư Tô đóng gói sẵn trên HuggingFace:
```bash
python3 scripts/download_all_to_sqlite.py
```
*Sau khi chạy xong, bạn sẽ thấy file `vietnamese_legal_documents.db` và `content_store.db` xuất hiện ở thư mục gốc.*

#### Bước 4: Import dữ liệu Án Lệ
Đưa toàn bộ thông tin Án Lệ Việt Nam vào cơ sở dữ liệu chính:
```bash
python3 scripts/import_anle.py
```

#### Bước 5: Import cấu trúc Pháp Điển
Đưa dữ liệu sơ đồ cấu trúc và nội dung các điều Pháp Điển vào cơ sở dữ liệu:
```bash
python3 scripts/import_phapdien.py
```

#### Bước 6: Phân tách cơ sở dữ liệu (Tối ưu RAM)
Nếu bước tải ở HuggingFace chưa phân tách sẵn, lệnh này sẽ quét qua DB chính, lọc toàn bộ phần nội dung HTML thô siêu nặng đẩy sang file `content_store.db` riêng biệt, giúp tối ưu hóa dung lượng RAM cho API Server:
```bash
python3 scripts/split_content_db.py
```

#### Bước 7: Tối ưu hóa hiệu năng SQLite & Tạo FTS5 Index
Tạo chỉ mục Full-Text Search giúp tìm kiếm từ khóa siêu tốc trên cơ sở dữ liệu, đồng thời chạy lệnh `VACUUM` để dọn dẹp dung lượng thừa:
```bash
python3 scripts/optimize_db.py
```

#### Bước 8: Di cư cấu trúc CSDL (Schema Migration)
Cập nhật các bảng thông tin, bổ sung các trường dữ liệu và chỉ mục cần thiết cho chatbot hoạt động:
```bash
python3 scripts/upgrade_db.py
```

#### Bước 9: Xây dựng mối liên kết chéo pháp lý
Phân tích văn bản và thiết lập các mối liên kết chéo hướng ngang, hướng dọc giữa 153k văn bản pháp luật:
```bash
python3 scripts/build_crosslinks.py
```

#### Bước 10: Phân tách văn bản thành các Chunk nhỏ (Chuẩn bị cho Vector)
Cắt nhỏ các văn bản pháp luật dài thành các đoạn chunk nhỏ tối đa 512 tokens để chuẩn bị cho quá trình tạo embeddings:
```bash
python3 scratch/build_chunks_v2.py
```

#### Bước 11: Sinh Vector Embeddings & Xây dựng Chỉ mục FAISS (Mất nhiều thời gian ⏳)
Đây là bước nặng nhất của dự án. Hệ thống sẽ quét qua toàn bộ 1.55 triệu chunks văn bản, gửi qua mô hình Bi-Encoder để sinh các vector 768 chiều, lưu cache vào `vector_store.db` và nạp vào chỉ mục tìm kiếm FAISS `chunks_faiss.index`.
*   **Thời gian thực hiện:** Khoảng 8 - 12 tiếng nếu chạy bằng CPU. Khoảng 1 - 2 tiếng nếu chạy bằng Apple Silicon GPU hoặc NVIDIA CUDA GPU.
*   **Giải pháp chạy nền:** Để không bị ngắt quãng khi tắt cửa sổ Terminal hoặc mất kết nối SSH, hãy chạy lệnh này dưới dạng tiến trình ngầm (background process):
```bash
nohup python3 scripts/build_vector_index.py > logs/vector_build.log 2>&1 &
```

##### 📊 Cách Giám Sát Tiến Độ Sinh Vector:
Bạn có thể chạy script giám sát trạng thái để xem tiến độ (%) đã hoàn thành, tốc độ tức thời và thời gian dự kiến hoàn thành còn lại:
```bash
python3 status.py
```
*Màn hình sẽ hiển thị thanh tiến độ trực quan như sau:*
```text
┌────────────────────────────────────────────────────────────────────────┐
│  2. TIẾN ĐỘ THỰC HIỆN VECTOR EMBEDDINGS (PHASE 2)                      │
├────────────────────────────────────────────────────────────────────────┤
│  • Tiến độ: [████████████████--------------] 55.03%                    │
│  • Tổng document chunks:  1,553,757                                    │
│  • Vector đã sinh (cache): 855,096                                     │
│  • Tốc độ tức thời:       57.8 chunks/s                                │
│  • Dự kiến hoàn thành:    3.36 giờ (201.4 phút)                        │
└────────────────────────────────────────────────────────────────────────┘
```

#### Bước 12: Khởi chạy API Server
Sau khi quá trình sinh vector hoàn tất (Tiến độ đạt 100% trên `status.py`), bạn khởi chạy server API chính thức trên cổng `2004`:
```bash
# Đặt biến PRELOAD_SMART_SEARCH=1 nếu muốn preload mô hình AI lên RAM ngay khi khởi động
# Hoặc để mặc định (lazy-load khi có request đầu tiên để tiết kiệm RAM)
python3 server.py
```

---

## 📡 Các API Endpoints Chính

Hệ thống cung cấp Swagger UI tài liệu tương tác trực quan đầy đủ tại địa chỉ: **`http://localhost:2004/docs`**

### 🤖 Chatbot AI & RAG (`/assistant`)
*   `POST /assistant/chat`: Gửi câu hỏi pháp luật. Nhận câu trả lời kèm danh sách các văn bản trích dẫn (`citations`) chuẩn xác 100%. Hỗ trợ phiên hội thoại (`session_id`).
*   `GET /assistant/providers`: Xem trạng thái các nhà cung cấp LLM đang khả dụng.
*   `POST /assistant/switch-provider`: Thay đổi nhanh nhà cung cấp LLM (Ví dụ chuyển từ Gemini sang OpenAI) ngay lập tức mà không cần khởi động lại máy chủ.
*   `GET /assistant/user-profile/{user_id}`: Kiểm tra hồ sơ trí nhớ dài hạn (sở thích pháp lý, thông tin đã nhớ) mà Mem0 đã học được về người dùng.

### 🔍 Tra Cứu & Tìm Kiếm (`/laws`)
*   `GET /laws/search`: Tìm kiếm văn bản pháp luật truyền thống (FTS5 BM25) hỗ trợ lọc theo loại, lĩnh vực, cơ quan ban hành, tình trạng hiệu lực.
*   `GET /laws/smart-search`: Tìm kiếm thông minh bằng ngữ nghĩa Dense Vector (FAISS). Trả về danh sách văn bản có nội dung tương đồng về ý nghĩa với câu hỏi dù không trùng từ khóa thô.
*   `GET /laws/{id}`: Xem thông tin chi tiết và nội dung HTML toàn văn của văn bản.
*   `GET /laws/{id}/relationships`: Lấy danh sách toàn bộ các văn bản có quan hệ pháp lý liên kết với văn bản hiện tại.
*   `GET /laws/{id}/lineage`: Trả về dữ liệu cây phả hệ pháp lý hướng dọc và hướng ngang dạng cấu trúc JSON Node/Edge (Dành cho vẽ biểu đồ mạng lưới vis-network).

### ⚖️ Phân Hệ Khác
*   `GET /anle/search`: Tìm kiếm FTS5 trong kho tài liệu Án Lệ và Bản Án.
*   `GET /phapdien/search`: Tìm kiếm các Điều khoản nằm trong hệ thống Pháp Điển Việt Nam.

---

## 🤖 Cấu Hình Model Context Protocol (MCP) Server

Để Cursor hoặc Claude Desktop của bạn có thể tự động đọc hiểu, tìm kiếm và trích dẫn trực tiếp từ kho dữ liệu 153.000 văn bản luật Việt Nam cục bộ trên máy của bạn:

### Cấu hình trong Cursor:
Vào `Settings` -> `Models` -> `MCP` -> Click `+ Add New MCP Server`:
*   **Name:** `dataluatvn-mcp`
*   **Type:** `stdio`
*   **Command:** `python3`
*   **Args:** `/Users/<TÊN_USER_CỦA_BẠN>/.../luatvietnam/mcp_server.py`

### Cấu hình trong Claude Desktop:
Mở file cấu hình Claude Desktop tại `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) hoặc `%APPDATA%\Claude\claude_desktop_config.json` (Windows) và thêm:
```json
{
  "mcpServers": {
    "dataluatvn-mcp": {
      "command": "python3",
      "args": [
        "/Users/<ĐƯỜNG_DẪN_DỰ_ÁN>/luatvietnam/mcp_server.py"
      ],
      "env": {
        "DB_PATH": "/Users/<ĐƯỜNG_DẪN_DỰ_ÁN>/luatvietnam/vietnamese_legal_documents.db",
        "CONTENT_DB_PATH": "/Users/<ĐƯỜNG_DẪN_DỰ_ÁN>/luatvietnam/content_store.db"
      }
    }
  }
}
```

---

## 🔒 Bản Quyền & Phát Triển
Dự án được phát triển và vận hành bởi **Pháp sư Tô** cùng đội ngũ cộng tác viên dữ liệu. Mọi đóng góp về mã nguồn hoặc phản hồi lỗi dữ liệu xin vui lòng tạo Issue hoặc gửi Pull Request trên GitHub.
