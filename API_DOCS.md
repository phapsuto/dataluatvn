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

## 🛠️ Tích Hợp Frontend (Javascript Ví Dụ)

Dưới đây là đoạn code JS mẫu để gọi API Tìm kiếm:

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

## 📖 Swagger UI
Tài liệu tương tác trực tiếp (cho phép test API ngay trên trình duyệt) được tự động tạo tại:
- **Swagger UI:** `http://[IP_SERVER]:2004/docs`
- **ReDoc:** `http://[IP_SERVER]:2004/redoc`
