# 📚 Tài Liệu API - DataLuatVN

Tài liệu này cung cấp hướng dẫn chi tiết cách kết nối và sử dụng các API của hệ thống Dữ liệu Pháp luật Việt Nam.

## 🔐 Xác Thực (Authentication)

Tất cả các endpoint truy xuất dữ liệu luật (bắt đầu bằng `/laws/`) **đều yêu cầu API Key**.

Bạn có 2 cách để truyền API Key:
1. **Qua Header (Khuyên dùng):** Thêm header `X-API-Key: dlvn_xxxxxxxxxxxxxxxxxxxxxxxx`
2. **Qua Query Parameter:** Thêm `?api_key=dlvn_xxxxxxxxxxxxxxxxxxxxxxxx` vào cuối URL.

*Để tạo API Key, hãy truy cập trang quản trị tại: `http://[IP_SERVER]:2004/admin`*

---

## 🚀 Các Endpoints Chính

### 1. Kiểm tra trạng thái hệ thống
- **Endpoint:** `GET /`
- **Xác thực:** Không yêu cầu
- **Mô tả:** Trả về trạng thái hoạt động của server và tổng số văn bản hiện có trong CSDL.

### 2. Tìm kiếm và Lọc văn bản (Có hỗ trợ Full-Text Search)
- **Endpoint:** `GET /laws/search`
- **Xác thực:** Yêu cầu API Key
- **Mô tả:** Tìm kiếm văn bản theo từ khóa và các bộ lọc. Hệ thống sử dụng **Full-Text Search (FTS5)** nên sẽ tự động sắp xếp các kết quả có độ liên quan cao nhất (relevance) lên đầu nếu bạn truyền từ khóa `q`.

**Tham số (Query Parameters):**
| Tham số | Bắt buộc | Kiểu | Mô tả |
|---|---|---|---|
| `q` | Không | string | Từ khóa tìm kiếm (khớp với tiêu đề hoặc số ký hiệu). |
| `loai_van_ban` | Không | string | Lọc theo loại (VD: "Luật", "Nghị định"). |
| `co_quan_ban_hanh` | Không | string | Lọc theo cơ quan (VD: "Quốc hội"). |
| `tinh_trang` | Không | string | Tình trạng hiệu lực (VD: "Còn hiệu lực"). |
| `linh_vuc` | Không | string | Lọc theo lĩnh vực pháp luật. |
| `limit` | Không | int | Số lượng kết quả tối đa (Mặc định: 20, Max: 100). |
| `offset` | Không | int | Vị trí bắt đầu (dùng cho phân trang). |
| `require_content`| Không | bool | Truyền `true` để bộ lọc tự động loại bỏ các văn bản cũ không có ruột HTML. Đảm bảo 100% kết quả trả về có thể xem toàn văn. |

**Cấu trúc Phân trang (Pagination) trả về:**
```json
{
  "total": 1399,
  "limit": 20,
  "offset": 0,
  "total_pages": 70,
  "current_page": 1,
  "has_next": true,
  "has_previous": false,
  "results": [ ... ]
}
```

**Ví dụ cURL:**
```bash
curl -H "X-API-Key: dlvn_123456" "http://localhost:2004/laws/search?q=đất+đai&require_content=true"
```

### 3. Lấy Chi Tiết Toàn Văn
- **Endpoint:** `GET /laws/{law_id}`
- **Xác thực:** Yêu cầu API Key
- **Mô tả:** Lấy toàn bộ metadata và nội dung HTML dài của văn bản.

**Ví dụ cURL:**
```bash
curl -H "X-API-Key: dlvn_123456" http://localhost:2004/laws/38920
```

### 4. Tra Cứu Quan Hệ Pháp Lý
- **Endpoint:** `GET /laws/{law_id}/relationships`
- **Xác thực:** Yêu cầu API Key
- **Mô tả:** Trả về danh sách các văn bản có liên quan (VD: văn bản thay thế, văn bản hướng dẫn, bị sửa đổi...).

**Ví dụ cURL:**
```bash
curl -H "X-API-Key: dlvn_123456" http://localhost:2004/laws/38920/relationships
```

### 5. Lấy Danh Mục (Dropdown)
Các endpoint này dùng để render bộ lọc cho Frontend.
- **Loại văn bản:** `GET /laws/categories/types`
- **Lĩnh vực:** `GET /laws/categories/fields`
- **Cơ quan ban hành:** `GET /laws/categories/agencies`

**Xác thực:** Yêu cầu API Key

---

### 6. Tra Cứu Án Lệ & Bản Án
- **Tìm kiếm:** `GET /anle/search?q=từ_khóa`
- **Xem chi tiết:** `GET /anle/{doc_name}`
- **Thống kê:** `GET /anle/stats`
- **Danh mục:** `GET /anle/categories/case-types` và `GET /anle/categories/court-levels`

**Xác thực:** Yêu cầu API Key

### 7. Tra Cứu Bộ Pháp Điển
- **Tìm kiếm:** `GET /phapdien/search?q=từ_khóa`
- **Xem chi tiết:** `GET /phapdien/{article_anchor}`
- **Danh mục đề mục:** `GET /phapdien/subjects`
- **Danh mục chủ đề:** `GET /phapdien/topics`
- **Thuật ngữ (Glossary):** `GET /phapdien/glossary`
- **Thống kê:** `GET /phapdien/stats`

**Xác thực:** Yêu cầu API Key

---

## 🛠️ Admin CRUD API (Quản trị dữ liệu)

Các endpoint này dành cho **admin** để tạo mới, chỉnh sửa, xóa dữ liệu pháp luật khi phát hiện sai sót.

**Xác thực:** Yêu cầu **JWT Bearer Token** (đăng nhập admin tại `/admin`).

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 8. CRUD Văn bản Pháp luật

#### Tạo văn bản mới
- **Endpoint:** `POST /admin/laws`
- **Body (JSON):**

| Trường | Bắt buộc | Kiểu | Mô tả |
|---|---|---|---|
| `title` | ✅ | string | Tiêu đề văn bản |
| `so_ky_hieu` | Không | string | Số ký hiệu (VD: "01/2024/NĐ-CP") |
| `ngay_ban_hanh` | Không | string | Ngày ban hành |
| `loai_van_ban` | Không | string | Loại văn bản |
| `co_quan_ban_hanh` | Không | string | Cơ quan ban hành |
| `tinh_trang_hieu_luc` | Không | string | Tình trạng hiệu lực |
| `ngay_co_hieu_luc` | Không | string | Ngày có hiệu lực |
| `ngay_het_hieu_luc` | Không | string | Ngày hết hiệu lực |
| `nganh` | Không | string | Ngành |
| `linh_vuc` | Không | string | Lĩnh vực |
| `nguoi_ky` | Không | string | Người ký |
| `chuc_danh` | Không | string | Chức danh |
| `pham_vi` | Không | string | Phạm vi |
| `nguon_thu_thap` | Không | string | Nguồn thu thập |
| `ngay_dang_cong_bao` | Không | string | Ngày đăng công báo |
| `thong_tin_ap_dung` | Không | string | Thông tin áp dụng |
| `content_html` | Không | string | Nội dung HTML toàn văn |

**Ví dụ cURL:**
```bash
curl -X POST http://localhost:2004/admin/laws \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Luật Đất đai năm 2024",
    "so_ky_hieu": "31/2024/QH15",
    "loai_van_ban": "Luật",
    "co_quan_ban_hanh": "Quốc hội",
    "tinh_trang_hieu_luc": "Còn hiệu lực"
  }'
```

**Response:**
```json
{
  "ok": true,
  "message": "Đã tạo văn bản ID 99999",
  "id": "99999"
}
```

#### Cập nhật văn bản
- **Endpoint:** `PUT /admin/laws/{law_id}`
- **Body:** Chỉ gửi các trường cần sửa (partial update).

```bash
curl -X PUT http://localhost:2004/admin/laws/38920 \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"tinh_trang_hieu_luc": "Hết hiệu lực toàn bộ", "nguoi_ky": "Nguyễn Văn A"}'
```

#### Xóa văn bản
- **Endpoint:** `DELETE /admin/laws/{law_id}`
- **Lưu ý:** Xóa vĩnh viễn bản ghi + FTS index + relationships + content HTML.

```bash
curl -X DELETE http://localhost:2004/admin/laws/38920 \
  -H "Authorization: Bearer YOUR_JWT"
```

---

### 9. CRUD Án Lệ & Bản Án

#### Tạo Án Lệ mới
- **Endpoint:** `POST /admin/anle`
- **Body (JSON):**

| Trường | Bắt buộc | Kiểu | Mô tả |
|---|---|---|---|
| `doc_name` | ✅ | string | Mã văn bản (unique) |
| `title` | ✅ | string | Tiêu đề bản án |
| `doc_code` | Không | string | Số hiệu |
| `doc_type` | Không | string | Loại văn bản |
| `case_type` | Không | string | Loại vụ án |
| `doc_subtype` | Không | string | Phân loại phụ |
| `year` | Không | int | Năm |
| `issue_date` | Không | string | Ngày ban hành |
| `issuing_authority` | Không | string | Cơ quan ban hành |
| `court_level` | Không | string | Cấp tòa |
| `jurisdiction` | Không | string | Thẩm quyền |
| `subject` | Không | string | Chủ đề |
| `markdown` | Không | string | Toàn văn markdown |
| `precedent_number` | Không | string | Số Án Lệ |
| `adopted_date` | Không | string | Ngày thông qua |
| `applied_article_code` | Không | string | Mã điều luật áp dụng |
| `principle_text` | Không | string | Nguyên tắc pháp lý |
| `pdf_url` | Không | string | URL file PDF |

**Ví dụ cURL:**
```bash
curl -X POST http://localhost:2004/admin/anle \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_name": "AL-2024-01",
    "title": "Án lệ số 01/2024/AL về tranh chấp đất đai",
    "case_type": "Dân sự",
    "court_level": "Tòa án nhân dân tối cao",
    "year": 2024,
    "precedent_number": "01/2024/AL"
  }'
```

#### Cập nhật Án Lệ
- **Endpoint:** `PUT /admin/anle/{doc_name}`

```bash
curl -X PUT http://localhost:2004/admin/anle/AL-2024-01 \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"court_level": "TAND Cấp cao tại Hà Nội"}'
```

#### Xóa Án Lệ
- **Endpoint:** `DELETE /admin/anle/{doc_name}`

```bash
curl -X DELETE http://localhost:2004/admin/anle/AL-2024-01 \
  -H "Authorization: Bearer YOUR_JWT"
```

---

### 10. CRUD Bộ Pháp Điển

#### Tạo Điều khoản mới
- **Endpoint:** `POST /admin/phapdien`
- **Body (JSON):**

| Trường | Bắt buộc | Kiểu | Mô tả |
|---|---|---|---|
| `article_anchor` | ✅ | string | Mã định danh (unique) |
| `article_title` | ✅ | string | Tiêu đề Điều khoản |
| `chapter_title` | Không | string | Tiêu đề Chương |
| `subject_id` | Không | string | Mã Đề mục |
| `subject_title` | Không | string | Tên Đề mục |
| `topic_id` | Không | string | Mã Chủ đề |
| `topic_number` | Không | int | Số thứ tự |
| `topic_title` | Không | string | Tên Chủ đề |
| `content_text` | Không | string | Nội dung văn bản |
| `source_url` | Không | string | URL nguồn |
| `source_note_text` | Không | string | Ghi chú nguồn |
| `related_note_text` | Không | string | Ghi chú liên quan |

**Ví dụ cURL:**
```bash
curl -X POST http://localhost:2004/admin/phapdien \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "article_anchor": "dieu-1-luat-dat-dai-2024",
    "article_title": "Điều 1. Phạm vi điều chỉnh",
    "subject_title": "Đất đai",
    "content_text": "Luật này quy định về chế độ sở hữu đất đai..."
  }'
```

#### Cập nhật Điều khoản
- **Endpoint:** `PUT /admin/phapdien/{article_anchor}`

```bash
curl -X PUT http://localhost:2004/admin/phapdien/dieu-1-luat-dat-dai-2024 \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"content_text": "Nội dung đã được cập nhật..."}'
```

#### Xóa Điều khoản
- **Endpoint:** `DELETE /admin/phapdien/{article_anchor}`

```bash
curl -X DELETE http://localhost:2004/admin/phapdien/dieu-1-luat-dat-dai-2024 \
  -H "Authorization: Bearer YOUR_JWT"
```

---

### Response chung cho CRUD

Tất cả endpoints CRUD trả về cùng format:

```json
{
  "ok": true,
  "message": "Đã tạo/cập nhật/xóa ...",
  "id": "38920"
}
```

**Lỗi thường gặp:**

| HTTP Code | Mô tả |
|---|---|
| `401` | Chưa đăng nhập / JWT hết hạn |
| `404` | Không tìm thấy bản ghi |
| `409` | Trùng lặp (duplicate doc_name/article_anchor) |
| `422` | Dữ liệu gửi lên không hợp lệ |

---

## 🔗 Tích Hợp Frontend (Javascript Ví Dụ)

### Tra cứu dữ liệu (dùng API Key)

```javascript
const API_KEY = "dlvn_YOUR_API_KEY_HERE";
const BASE_URL = "http://localhost:2004";

async function searchLaws(keyword) {
    const url = new URL(`${BASE_URL}/laws/search`);
    url.searchParams.append("q", keyword);
    url.searchParams.append("require_content", "true");

    const response = await fetch(url, {
        method: "GET",
        headers: {
            "X-API-Key": API_KEY
        }
    });
    
    if (response.ok) {
        const data = await response.json();
        console.log(`Tìm thấy ${data.total} kết quả!`, data.results);
    } else {
        console.error("Lỗi xác thực hoặc server", await response.text());
    }
}
```

### Admin CRUD (dùng JWT)

```javascript
const JWT_TOKEN = "eyJhbGciOi..."; // Lấy từ POST /auth/login

// Cập nhật văn bản
async function updateLaw(lawId, changes) {
    const response = await fetch(`${BASE_URL}/admin/laws/${lawId}`, {
        method: "PUT",
        headers: {
            "Authorization": `Bearer ${JWT_TOKEN}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify(changes)
    });
    
    const result = await response.json();
    if (result.ok) {
        console.log("✅", result.message);
    } else {
        console.error("❌", result.detail || result.message);
    }
}

// Ví dụ: sửa tình trạng hiệu lực
updateLaw(38920, { tinh_trang_hieu_luc: "Hết hiệu lực toàn bộ" });
```

## 📖 Swagger UI
Tài liệu tương tác trực tiếp (cho phép test API ngay trên trình duyệt) được tự động tạo tại:
- **Swagger UI:** `http://[IP_SERVER]:2004/docs`
- **ReDoc:** `http://[IP_SERVER]:2004/redoc`

