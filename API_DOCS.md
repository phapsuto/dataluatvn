# 📚 Tài Liệu API - dataluatvn (LuatBot Ultimate)

Tài liệu này cung cấp đặc tả kỹ thuật chi tiết của tất cả các API Endpoint thuộc hệ thống Dữ liệu Pháp luật Việt Nam và AI Chatbot RAG 7 Tầng.

---

## 🔐 Xác Thực (Authentication)

Hệ thống cung cấp hai cơ chế xác thực riêng biệt tùy thuộc vào đối tượng sử dụng:

### 1. Dành cho Ứng dụng tích hợp (Sử dụng API Key)
Mọi endpoint tra cứu dữ liệu (bắt đầu bằng `/laws/`, `/anle/`, `/phapdien/`, `/assistant/`) đều yêu cầu phải truyền API Key hợp lệ.
Bạn có thể truyền API Key bằng 2 cách:
- **Cách 1 (Khuyên dùng):** Thêm Header `X-API-Key: dlvn_xxxxxxxxxxxxxxxxxxxxxxxx`
- **Cách 2:** Thêm tham số Query `?api_key=dlvn_xxxxxxxxxxxxxxxxxxxxxxxx` vào URL.
*Để tạo API Key mới, đăng nhập vào trang quản trị tại: `http://[IP_SERVER]:2004/admin`*

### 2. Dành cho Quản trị viên (Sử dụng JWT Bearer Token)
Các endpoint quản trị dữ liệu (bắt đầu bằng `/admin/`) yêu cầu xác thực bằng mã Token JWT:
- Header: `Authorization: Bearer <MÃ_JWT_TOKEN>`
*Lấy mã JWT bằng cách gọi API `POST /auth/login`.*

---

## 📡 1. Nhóm API AI Chatbot RAG 7 Tầng (`/assistant`)

Nhóm API kết nối trực tiếp với lõi xử lý AI thông minh tích hợp RAG 7 tầng, quản lý phiên và bộ nhớ người dùng.

### 1.1 Gửi câu hỏi cho Trợ lý ảo AI
Gửi câu hỏi pháp luật tự nhiên của người dùng, lõi RAG 7 tầng sẽ tự động định tuyến, truy xuất lai (BM25 + FAISS + HippoRAG Graph), sinh câu trả lời tự kiểm duyệt (FLARE) và khóa trích dẫn (P-Cite).

- **Endpoint:** `POST /assistant/chat`
- **Xác thực:** Yêu cầu API Key
- **Content-Type:** `application/json`
- **Body Request:**
  ```json
  {
    "prompt": "Quy định về việc sa thải nhân viên khi tự ý nghỉ việc 5 ngày?",
    "session_id": "session_user_99"
  }
  ```
  *Trong đó `session_id` (tùy chọn) dùng để chatbot ghi nhớ ngữ cảnh lịch sử chat của phiên hội thoại.*

- **Response (JSON):**
  ```json
  {
    "response": "Theo quy định tại Khoản 4 Điều 125 Bộ luật Lao động năm 2019 (Luật số 45/2019/QH14), người sử dụng lao động có quyền áp dụng hình thức xử lý kỷ luật sa thải đối với người lao động tự ý bỏ việc 05 ngày cộng dồn trong thời hạn 30 ngày hoặc 20 ngày cộng dồn trong thời hạn 365 ngày mà không có lý do chính đáng...",
    "citations": [
      {
        "id": 38920,
        "title": "Bộ luật Lao động năm 2019",
        "so_ky_hieu": "45/2019/QH14",
        "loai_van_ban": "Luật",
        "tinh_trang_hieu_luc": "Còn hiệu lực"
      }
    ],
    "domain": "civil_and_labor",
    "flare_activated": false,
    "search_count": 1
  }
  ```

### 1.2 Xem trạng thái các nhà cung cấp LLM
Lấy thông tin mô hình hiện tại đang được sử dụng chính, cấu hình chuỗi dự phòng (fallback) và danh sách các nhà cung cấp LLM được cấu hình trên server.

- **Endpoint:** `GET /assistant/providers`
- **Xác thực:** Yêu cầu API Key
- **Response (JSON):**
  ```json
  {
    "active_provider": "gemini",
    "active_model": "gemini-1.5-flash",
    "fallback_chain": ["cohere", "openai"],
    "providers_status": {
      "gemini": "ONLINE",
      "cohere": "ONLINE",
      "openai": "ONLINE"
    }
  }
  ```

### 1.3 Đổi LLM Provider tức thời (Runtime Hot-Swap)
Chuyển đổi mô hình LLM chính của chatbot ngay lập tức mà không cần khởi động lại máy chủ API.

- **Endpoint:** `POST /assistant/switch-provider`
- **Xác thực:** Yêu cầu API Key
- **Body Request:**
  ```json
  {
    "provider": "cohere"
  }
  ```
- **Response (JSON):**
  ```json
  {
    "ok": true,
    "message": "Đã chuyển đổi active provider sang cohere",
    "active_model": "command-r-plus"
  }
  ```

### 1.4 Xem hồ sơ ghi nhớ người dùng (Long-term Memory Profile)
Xem các thông tin chi tiết mà bộ nhớ dài hạn Mem0 đã học và lưu trữ về người dùng qua các phiên chat (VD: ngành nghề, vị trí địa lý, chủ đề luật quan tâm).

- **Endpoint:** `GET /assistant/user-profile/{user_id}`
- **Xác thực:** Yêu cầu API Key
- **Response (JSON):**
  ```json
  {
    "user_id": "session_user_99",
    "facts": [
      "Người dùng sở hữu doanh nghiệp trong lĩnh vực công nghệ thông tin.",
      "Người dùng quan tâm đến quy định về thuế giá trị gia tăng ở Tp. Hồ Chí Minh."
    ],
    "last_updated": "2026-06-08T14:35:10Z"
  }
  ```

---

## 📡 2. Nhóm API Văn Bản Pháp Luật (`/laws`)

Nhóm API quản lý dữ liệu văn bản quy phạm pháp luật, liên kết nguồn luật và tìm kiếm lai.

### 2.1 Tìm kiếm lai (FTS5 BM25 Search)
Tìm kiếm văn bản pháp luật truyền thống khớp từ khóa chính xác dựa trên công cụ Full-Text Search FTS5 của SQLite.

- **Endpoint:** `GET /laws/search`
- **Xác thực:** Yêu cầu API Key
- **Query Parameters:**
  *   `q` (string, optional): Từ khóa tìm kiếm.
  *   `loai_van_ban` (string, optional): Lọc loại văn bản (Luật, Nghị định, Thông tư...).
  *   `co_quan_ban_hanh` (string, optional): Cơ quan ban hành (Quốc hội, Chính phủ...).
  *   `tinh_trang` (string, optional): Tình trạng hiệu lực (Còn hiệu lực, Hết hiệu lực...).
  *   `linh_vuc` (string, optional): Lĩnh vực pháp luật.
  *   `limit` (int, optional, default=20, max=100): Giới hạn kết quả.
  *   `offset` (int, optional, default=0): Vị trí bắt đầu phân trang.
  *   `require_content` (bool, optional, default=false): Chỉ lấy văn bản có nội dung HTML thô.
- **Response (JSON):**
  ```json
  {
    "total": 142,
    "limit": 2,
    "offset": 0,
    "total_pages": 71,
    "current_page": 1,
    "has_next": true,
    "has_previous": false,
    "results": [
      {
        "id": 38920,
        "title": "Bộ luật Lao động năm 2019",
        "so_ky_hieu": "45/2019/QH14",
        "loai_van_ban": "Luật",
        "tinh_trang_hieu_luc": "Còn hiệu lực",
        "ngay_ban_hanh": "2019-11-20"
      }
    ]
  }
  ```

### 2.2 Tìm kiếm thông minh bằng ngữ nghĩa (Smart Semantic Search)
Tìm kiếm thông tin theo ý nghĩa câu hỏi bằng mô hình dense vector nhúng phối hợp chỉ mục FAISS. Trả về kết quả phù hợp ngay cả khi người dùng không dùng từ khóa chính xác trong luật.

- **Endpoint:** `GET /laws/smart-search`
- **Xác thực:** Yêu cầu API Key
- **Query Parameters:**
  *   `q` (string, required): Câu hỏi hoặc đoạn văn bản cần tìm kiếm ngữ nghĩa.
  *   `limit` (int, optional, default=5): Số lượng đoạn văn bản phù hợp muốn lấy.
- **Response (JSON):**
  ```json
  {
    "query": "quy định nghỉ phép năm của người lao động",
    "results": [
      {
        "chunk_id": 1058291,
        "law_id": 38920,
        "title": "Bộ luật Lao động năm 2019",
        "so_ky_hieu": "45/2019/QH14",
        "score": 0.892,
        "content_chunk": "Điều 113. Nghỉ hằng năm: Người lao động làm việc đủ 12 tháng cho một người sử dụng lao động thì được nghỉ hằng năm, hưởng nguyên lương theo hợp đồng lao động..."
      }
    ]
  }
  ```

### 2.3 Xem chi tiết toàn văn văn bản
Lấy thông tin siêu dữ liệu đầy đủ kèm nội dung toàn văn HTML thô lưu trong `content_store.db`.

- **Endpoint:** `GET /laws/{law_id}`
- **Xác thực:** Yêu cầu API Key
- **Response (JSON):**
  ```json
  {
    "id": 38920,
    "title": "Bộ luật Lao động năm 2019",
    "so_ky_hieu": "45/2019/QH14",
    "content_html": "<p><strong>Điều 1. Phạm vi điều chỉnh</strong>...</p>",
    "tinh_trang_hieu_luc": "Còn hiệu lực",
    "ngay_ban_hanh": "2019-11-20",
    "co_quan_ban_hanh": "Quốc hội",
    "loai_van_ban": "Luật",
    "nguoi_ky": "Nguyễn Thị Kim Ngân"
  }
  ```

### 2.4 Xem quan hệ liên kết pháp lý
Lấy danh sách các văn bản có quan hệ sửa đổi, thay thế, căn cứ ban hành hoặc hướng dẫn thi hành với văn bản hiện tại.

- **Endpoint:** `GET /laws/{law_id}/relationships`
- **Xác thực:** Yêu cầu API Key
- **Response (JSON):**
  ```json
  {
    "law_id": 38920,
    "relationships": [
      {
        "other_doc_id": 41250,
        "so_ky_hieu": "145/2020/NĐ-CP",
        "title": "Nghị định 145/2020/NĐ-CP quy định chi tiết và hướng dẫn thi hành một số điều của Bộ luật Lao động...",
        "relationship": "hướng dẫn thi hành"
      }
    ]
  }
  ```

### 2.5 Dữ liệu cây phả hệ pháp lý (Lineage Tree Node/Edge)
Trả về cấu trúc Node và Edge của mạng lưới phả hệ pháp lý liên kết với văn bản, phục vụ trực tiếp cho thư viện vẽ đồ thị tương tác phía Frontend (như `vis-network`).

- **Endpoint:** `GET /laws/{law_id}/lineage`
- **Xác thực:** Yêu cầu API Key
- **Response (JSON):**
  ```json
  {
    "nodes": [
      {
        "id": 38920,
        "label": "Bộ luật 45/2019/QH14",
        "title": "Bộ luật Lao động năm 2019",
        "color": "#10B981"
      },
      {
        "id": 41250,
        "label": "Nghị định 145/2020/NĐ-CP",
        "title": "Nghị định hướng dẫn thi hành Bộ luật Lao động...",
        "color": "#3B82F6"
      }
    ],
    "edges": [
      {
        "from": 41250,
        "to": 38920,
        "label": "hướng dẫn thi hành",
        "arrows": "to"
      }
    ]
  }
  ```

---

## 📡 3. Nhóm API Án Lệ (`/anle`)

Quản lý thông tin Án Lệ Việt Nam.

*   `GET /anle/stats`: Thống kê tổng số lượng án lệ.
*   `GET /anle/search?q=đất+đai`: Tìm kiếm án lệ bằng chỉ mục FTS5.
*   `GET /anle/{doc_name}`: Lấy chi tiết toàn văn nội dung án lệ định dạng Markdown.

---

## 📡 4. Nhóm API Pháp Điển (`/phapdien`)

Tra cứu cấu trúc Bộ Pháp Điển Việt Nam.

*   `GET /phapdien/stats`: Thống kê tổng số đề mục, chủ đề pháp điển.
*   `GET /phapdien/search?q=thuế`: Tìm kiếm nội dung điều khoản pháp điển.
*   `GET /phapdien/{article_anchor}`: Xem chi tiết điều khoản pháp điển theo khóa định danh.

---

## 🛠️ 5. Nhóm API Quản Trị Hệ Thống (`/admin`)

*Lưu ý: Tất cả các API dưới đây đều yêu cầu Header `Authorization: Bearer <JWT_TOKEN>`*

### 5.1 Đăng nhập lấy mã JWT
- **Endpoint:** `POST /auth/login`
- **Body Request (JSON):**
  ```json
  {
    "username": "admin",
    "password": "mật_khẩu_của_bạn"
  }
  ```
- **Response (JSON):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```

### 5.2 CRUD Văn bản Pháp luật

#### Thêm mới văn bản
- **Endpoint:** `POST /admin/laws`
- **Response:**
  ```json
  {
    "ok": true,
    "message": "Đã tạo văn bản ID 153421",
    "id": "153421"
  }
  ```

#### Cập nhật thông tin văn bản
- **Endpoint:** `PUT /admin/laws/{law_id}`
- **Body Request (JSON):** Gửi các trường cần chỉnh sửa (hỗ trợ partial update).
- **Response:**
  ```json
  {
    "ok": true,
    "message": "Đã cập nhật văn bản ID 38920",
    "id": "38920"
  }
  ```

#### Xóa văn bản
- **Endpoint:** `DELETE /admin/laws/{law_id}`
- **Response:**
  ```json
  {
    "ok": true,
    "message": "Đã xóa vĩnh viễn văn bản ID 38920",
    "id": "38920"
  }
  ```
