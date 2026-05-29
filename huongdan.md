# Hướng Dẫn Kết Nối & Khai Thác Kho Dữ Liệu Pháp Luật Việt Nam

Tài liệu này hướng dẫn chi tiết cách kết nối các ứng dụng, website, hoặc chatbot LLM của bạn với kho dữ liệu pháp luật 3.2 GB (`vietnamese_legal_documents.db`) thông qua 2 phương thức: **Kết nối trực tiếp vào SQLite DB** hoặc **Gọi qua REST API Server**.

---

## 📂 THÔNG TIN KHO DỮ LIỆU CỦA BẠN

*   **Tệp Database SQLite:** [vietnamese_legal_documents.db](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/vietnamese_legal_documents.db) (3.2 GB, chứa 153.420 văn bản và 897.890 mối liên kết).
*   **Mã nguồn máy chủ API:** [server.py](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/server.py) (Viết bằng FastAPI, chạy ngầm tại cổng `8080`).
*   **Trình cập nhật luật tự động:** [sync_new_laws.py](file:///Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/sync_new_laws.py) (Quét và tải luật mới từ cổng Chính phủ).

---

## 🔌 PHƯƠNG THỨC 1: GỌI QUA REST API SERVER (Khuyên Dùng)

Phương thức này phù hợp khi bạn xây dựng ứng dụng Frontend (React, Next.js), ứng dụng di động, các nền tảng chạy online, hoặc các AI Agent/Chatbot.

### 1. Khởi động Máy chủ API
Mặc định máy chủ đang chạy ngầm trên máy của bạn tại cổng `8080`. Nếu cần khởi động lại thủ công, bạn mở Terminal tại thư mục này và gõ:
```bash
python3 server.py
```
> [!TIP]
> Bạn có thể xem tài liệu tương tác trực quan (Swagger UI), thử nghiệm gọi API trực tiếp ngay trên trình duyệt tại địa chỉ: **[http://localhost:8080/docs](http://localhost:8080/docs)**.

### 2. Ví dụ kết nối bằng JavaScript / Node.js (Cho App Web, Frontend)
Sử dụng Fetch API để tìm kiếm 5 văn bản Luật Đất Đai còn hiệu lực:

```javascript
const searchLaws = async () => {
    const url = 'http://localhost:8080/laws/search?q=đất+đai&loai_van_ban=Luật&status=Còn+hiệu+lực&limit=5';
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        console.log("Danh sách văn bản tìm thấy:");
        data.forEach(law => {
            console.log(`- [${law.so_ky_hieu}] ${law.title} (${law.tinh_trang_hieu_luc})`);
        });
    } catch (error) {
        console.error("Lỗi kết nối API:", error);
    }
};

searchLaws();
```

### 3. Ví dụ kết nối bằng Python (Cho Backend, Tool AI)
Sử dụng thư viện `requests` để lấy chi tiết toàn văn điều luật qua ID văn bản:

```python
import requests

def get_law_detail(law_id):
    url = f"http://localhost:8080/laws/{law_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            law = response.json()
            print(f"Tiêu đề: {law['title']}")
            print(f"Số hiệu: {law['so_ky_hieu']}")
            # In ra 500 ký tự đầu tiên của nội dung điều luật HTML
            print(f"Nội dung (HTML): {law['content_html'][:500]}...")
        else:
            print(f"Không tìm thấy văn bản. Mã lỗi: {response.status_code}")
    except Exception as e:
        print(f"Lỗi kết nối API: {e}")

# Gọi thử với ID bất kỳ
get_law_detail(12345)
```

---

## 🗄️ PHƯƠNG THỨC 2: KẾT NỐI TRỰC TIẾP VÀO DATABASE SQLITE

Phương thức này phù hợp khi các ứng dụng/công cụ của bạn chạy **trên cùng một máy tính/máy chủ** với tệp database này và bạn muốn có hiệu năng tối đa mà không qua môi trường mạng HTTP.

### 1. Ví dụ kết nối bằng Python (Zero-dependency)
Sử dụng thư viện `sqlite3` có sẵn của Python để truy vấn dữ liệu cực kỳ nhanh:

```python
import sqlite3
import os

DB_PATH = "vietnamese_legal_documents.db"

def search_laws_direct(keyword, limit=5):
    if not os.path.exists(DB_PATH):
        print("Không tìm thấy file database!")
        return []
        
    # Kết nối trực tiếp vào file SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Định dạng kết quả dạng dict
    cursor = conn.cursor()
    
    query = """
        SELECT id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, tinh_trang_hieu_luc 
        FROM documents 
        WHERE (title LIKE ? OR so_ky_hieu LIKE ?) 
          AND tinh_trang_hieu_luc = 'Còn hiệu lực' 
        LIMIT ?
    """
    
    cursor.execute(query, (f"%{keyword}%", f"%{keyword}%", limit))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

# Chạy thử tìm kiếm
results = search_laws_direct("hình sự")
for res in results:
    print(f"- {res['so_ky_hieu']} | {res['title']}")
```

### 2. Ví dụ kết nối bằng Node.js (Sử dụng thư viện `better-sqlite3`)
Cài đặt thư viện: `npm install better-sqlite3`

```javascript
const Database = require('better-sqlite3');
const path = require('path');

const dbPath = path.resolve(__dirname, 'vietnamese_legal_documents.db');
const db = new Database(dbPath, { verbose: console.log });

// Truy vấn lấy các văn bản liên quan của một văn bản qua ID
const getRelationships = (lawId) => {
    const query = `
        SELECT r.relationship, d.title, d.so_ky_hieu
        FROM relationships r
        JOIN documents d ON r.other_doc_id = d.id
        WHERE r.doc_id = ?
    `;
    const stmt = db.prepare(query);
    const rows = stmt.all(lawId);
    return rows;
};

const relations = getRelationships(122880);
console.log(relations);
```

---

## 🤖 ỨNG DỤNG LÀM CHATBOT LLM / RAG PIPELINE

Để chatbot của bạn trả lời cực kỳ thông minh và trích dẫn chuẩn xác văn bản pháp luật, quy trình hoạt động (RAG Pipeline) sẽ được thiết lập như sau:

```text
[Người Dùng Hỏi] 
       ↓
[Trích xuất từ khóa hoặc Tạo Vector nhúng của câu hỏi]
       ↓
[Gọi API Search: http://localhost:8080/laws/search?q=từ_khóa&status=Còn+hiệu+lực]
       ↓
[Lấy ra top 3 văn bản phù hợp nhất]
       ↓
[Gọi API Detail: http://localhost:8080/laws/{id} để lấy toàn văn HTML/chữ sạch của 3 luật đó]
       ↓
[Nạp toàn bộ văn bản luật này vào phần Context (Ngữ cảnh) của LLM]
       ↓
[Prompt gửi LLM]:
"Bạn là Trợ lý pháp luật Việt Nam. Dựa vào các thông tin pháp lý chính xác được cung cấp dưới đây:
---
{Nội dung toàn văn các luật đã lấy từ API}
---
Hãy trả lời câu hỏi sau của người dùng một cách chuyên nghiệp, chính xác và ghi rõ trích dẫn điều khoản:
{Câu hỏi của người dùng}"
       ↓
[Chatbot phản hồi câu trả lời chuẩn xác 100% cho người dùng]
```

---

## 🔄 CẬP NHẬT DỮ LIỆU ĐỊNH KỲ

Để giữ cho kho dữ liệu luôn mới nhất, định kỳ bạn chỉ cần kích hoạt script cập nhật tự động bằng cách gõ lệnh sau trong Terminal (hoặc thiết lập crontab tự động chạy ngầm như trong file hướng dẫn kế hoạch):

```bash
python3 sync_new_laws.py
```
Mọi thông tin cập nhật sẽ được ghi tự động vào file `sync.log` của bạn để tiện theo dõi.
