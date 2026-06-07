#!/usr/bin/env python3
"""
mcp_server.py — Cổng kết nối Model Context Protocol (MCP) cho Claude Desktop / Cursor.
Chạy qua luồng STDIO bằng chuẩn JSON-RPC 2.0 (Zero-dependency).
"""

import sys
import json
import sqlite3
import re
import os

DB_NAME = os.environ.get("DB_PATH", "vietnamese_legal_documents.db")
CONTENT_DB = os.environ.get("CONTENT_DB_PATH", "content_store.db")

def log(msg: str):
    """Ghi debug log vào stderr (stdout dành riêng cho JSON-RPC)."""
    sys.stderr.write(f"[dataluatvn-mcp] {msg}\n")
    sys.stderr.flush()

def get_db():
    if not os.path.exists(DB_NAME):
        raise FileNotFoundError(f"Không tìm thấy database chính: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_content_db():
    if os.path.exists(CONTENT_DB):
        conn = sqlite3.connect(CONTENT_DB, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn
    return None

def clean_html(html_str: str) -> str:
    """Chuyển đổi nội dung HTML thô sang dạng Text sạch dễ đọc cho LLM."""
    if not html_str:
        return ""
    # Thay thế thẻ ngắt khối bằng dòng mới
    text = re.sub(r'</?(p|div|tr|h1|h2|h3|h4|h5|h6|br|li)[^>]*>', '\n', html_str)
    # Loại bỏ toàn bộ các thẻ HTML khác
    text = re.sub(r'<[^>]+>', '', text)
    # Chuẩn hóa khoảng trắng và dòng trống
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def send_response(response_dict: dict):
    """Gửi phản hồi JSON-RPC qua stdout."""
    sys.stdout.write(json.dumps(response_dict) + "\n")
    sys.stdout.flush()

def handle_tool_call(name: str, arguments: dict) -> dict:
    """Xử lý gọi công cụ từ phía AI client."""
    log(f"Gọi công cụ: {name} với tham số: {arguments}")
    
    if name == "search_laws":
        q = arguments.get("q")
        loai_van_ban = arguments.get("loai_van_ban")
        tinh_trang = arguments.get("tinh_trang")
        limit = min(int(arguments.get("limit", 5)), 50)
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            where_clauses = ["documents_fts MATCH ?"]
            params = [f'"{q}"']
            
            if loai_van_ban:
                where_clauses.append("d.loai_van_ban = ?")
                params.append(loai_van_ban)
            if tinh_trang:
                where_clauses.append("d.tinh_trang_hieu_luc = ?")
                params.append(tinh_trang)
                
            where_sql = " AND ".join(where_clauses)
            sql = f"""
                SELECT d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.loai_van_ban, d.co_quan_ban_hanh, d.tinh_trang_hieu_luc
                FROM documents d
                JOIN documents_fts ON d.id = documents_fts.rowid
                WHERE {where_sql}
                ORDER BY documents_fts.rank
                LIMIT ?
            """
            cursor.execute(sql, params + [limit])
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            
            text_out = []
            for r in rows:
                text_out.append(
                    f"⚖️ ID: {r['id']} | Số ký hiệu: {r['so_ky_hieu'] or 'Không số'}\n"
                    f"   Tiêu đề: {r['title']}\n"
                    f"   Ban hành: {r['co_quan_ban_hanh']} ({r['ngay_ban_hanh']}) | Trạng thái: {r['tinh_trang_hieu_luc']}"
                )
                
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n\n".join(text_out) if text_out else "Không tìm thấy văn bản nào phù hợp."
                    }
                ]
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Lỗi tra cứu: {str(e)}"}]}

    elif name == "get_document":
        doc_id = arguments.get("id")
        so_ky_hieu = arguments.get("so_ky_hieu")
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            if doc_id:
                cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            elif so_ky_hieu:
                cursor.execute("SELECT * FROM documents WHERE so_ky_hieu = ?", (so_ky_hieu,))
            else:
                conn.close()
                return {"content": [{"type": "text", "text": "Lỗi: Vui lòng nhập 'id' hoặc 'so_ky_hieu'."}]}
                
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return {"content": [{"type": "text", "text": "Không tìm thấy văn bản pháp luật yêu cầu."}]}
                
            doc = dict(row)
            content_html = doc.get("content_html")
            
            # Đọc từ content_store.db nếu trường content_html ở DB chính rỗng
            if not content_html:
                c_conn = get_content_db()
                if c_conn:
                    c_cursor = c_conn.cursor()
                    c_cursor.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (doc["id"],))
                    c_row = c_cursor.fetchone()
                    c_conn.close()
                    if c_row:
                        content_html = c_row["content_html"]
                        
            clean_text = clean_html(content_html) if content_html else "Văn bản chưa có nội dung toàn văn trong hệ thống."
            
            meta_str = (
                f"=== THÔNG TIN VĂN BẢN ===\n"
                f"ID: {doc['id']}\n"
                f"Tiêu đề: {doc['title']}\n"
                f"Số ký hiệu: {doc['so_ky_hieu'] or 'N/A'}\n"
                f"Loại văn bản: {doc['loai_van_ban'] or 'N/A'}\n"
                f"Cơ quan ban hành: {doc['co_quan_ban_hanh'] or 'N/A'}\n"
                f"Ngày ban hành: {doc['ngay_ban_hanh'] or 'N/A'}\n"
                f"Ngày có hiệu lực: {doc.get('ngay_co_hieu_luc') or 'N/A'}\n"
                f"Tình trạng hiệu lực: {doc['tinh_trang_hieu_luc'] or 'N/A'}\n"
                f"Lĩnh vực: {doc.get('linh_vuc') or 'N/A'}\n"
                f"\n=== TOÀN VĂN SẠCH (TEXT CỐT LÕI) ===\n"
                f"{clean_text}"
            )
            
            return {
                "content": [{"type": "text", "text": meta_str}]
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Lỗi đọc văn bản: {str(e)}"}]}

    elif name == "get_law_lineage":
        doc_id = arguments.get("id")
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, title, so_ky_hieu FROM documents WHERE id = ?", (doc_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                conn.close()
                return {"content": [{"type": "text", "text": "Không tìm thấy văn bản cần tra phả hệ."}]}
            doc = dict(doc_row)
            
            # Tìm quan hệ trực tiếp
            cursor.execute("""
                SELECT r.relationship, d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.tinh_trang_hieu_luc
                FROM relationships r
                JOIN documents d ON r.other_doc_id = d.id
                WHERE r.doc_id = ?
                UNION
                SELECT r.relationship, d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.tinh_trang_hieu_luc
                FROM relationships r
                JOIN documents d ON r.doc_id = d.id
                WHERE r.other_doc_id = ?
            """, (doc_id, doc_id))
            
            rows = cursor.fetchall()
            conn.close()
            
            out = [f"🌲 CÂY PHẢ HỆ VĂN BẢN: #{doc['id']} ({doc['so_ky_hieu'] or 'Không số'})\nTiêu đề: {doc['title']}\n"]
            for r in rows:
                out.append(
                    f"- Mối liên kết: [{r[0]}]\n"
                    f"  Văn bản: ID {r[1]} | Số ký hiệu: {r[3] or 'N/A'}\n"
                    f"  Tiêu đề: {r[2]}\n"
                    f"  Ban hành: {r[4]} | Trạng thái: {r[5]}"
                )
                
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n\n".join(out) if len(out) > 1 else "Văn bản hiện tại không có mối liên kết phả hệ nào trong CSDL."
                    }
                ]
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Lỗi tra phả hệ: {str(e)}"}]}

    elif name == "check_law_overlaps":
        doc_id = arguments.get("id")
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            target_row = cursor.fetchone()
            if not target_row:
                conn.close()
                return {"content": [{"type": "text", "text": "Không tìm thấy văn bản cần đối soát chồng chéo."}]}
            
            target_doc = dict(target_row)
            linh_vuc = target_doc.get("linh_vuc")
            title = target_doc.get("title") or ""
            
            # Trích xuất từ khóa tiêu đề
            words = re.findall(r'\w+', title.lower())
            stopwords = {"về", "việc", "của", "và", "trong", "tại", "cho", "để", "ban", "hành", "nội", "dung", "một", "số", "quy", "định", "sửa", "đổi", "bổ", "sung", "áp", "dụng", "các", "như", "theo", "văn", "bản"}
            keywords = [w for w in words if w not in stopwords and len(w) > 2][:3]
            
            candidates = []
            
            # Lấy liên kết trực tiếp còn hiệu lực
            cursor.execute("""
                SELECT d.*, r.relationship 
                FROM relationships r
                JOIN documents d ON (r.other_doc_id = d.id OR r.doc_id = d.id)
                WHERE (r.doc_id = ? OR r.other_doc_id = ?) 
                  AND d.id != ?
                  AND d.tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Hết hiệu lực một phần')
                LIMIT 10
            """, (doc_id, doc_id, doc_id))
            for r in cursor.fetchall():
                candidates.append(dict(r))
                
            # Lấy các văn bản cùng ngành có tiêu đề tương đương bằng FTS5
            if keywords:
                fts_query = " OR ".join([f'"{kw}"' for kw in keywords])
                try:
                    sql = """
                        SELECT d.*, 'Cùng lĩnh vực' as relationship
                        FROM documents d
                        JOIN documents_fts f ON d.id = f.rowid
                        WHERE d.id != ?
                          AND d.tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Hết hiệu lực một phần')
                          AND f.title MATCH ?
                    """
                    params = [doc_id, fts_query]
                    if linh_vuc:
                        sql += " AND d.linh_vuc = ?"
                        params.append(linh_vuc)
                    sql += " LIMIT 8"
                    cursor.execute(sql, params)
                    for r in cursor.fetchall():
                        d = dict(r)
                        if not any(c['id'] == d['id'] for c in candidates):
                            candidates.append(d)
                except sqlite3.OperationalError:
                    pass
            
            conn.close()
            
            # Thực hiện import module legal_logic để đối soát Điều 156
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from app.utils.legal_logic import compare_hierarchy
            
            out = [
                f"⚖️ ĐỐI SOÁT CHỒNG CHÉO & XUNG ĐỘT QUY ĐỊNH (ĐIỀU 156 LUẬT BAN HÀNH VBQPPL)\n"
                f"Văn bản gốc: #{target_doc['id']} | {target_doc['so_ky_hieu'] or 'Không số'} - {target_doc['title']}\n"
            ]
            
            for cand in candidates:
                res = compare_hierarchy(target_doc, cand)
                pref_text = "👍 ƯU TIÊN ÁP DỤNG" if res["preferred"]["id"] == cand["id"] else "❌ KHÔNG ƯU TIÊN (Bị lấn át)"
                
                out.append(
                    f"--------------------------------------------------\n"
                    f"👉 Đối chứng: #{cand['id']} | {cand['so_ky_hieu'] or 'N/A'}\n"
                    f"   Tiêu đề: {cand['title']}\n"
                    f"   Mối liên hệ: {cand.get('relationship', 'Cùng ngành/lĩnh vực')}\n"
                    f"   Kết luận hiệu lực: {pref_text}\n"
                    f"   Lý do: {res['reason']}\n"
                    f"   Căn cứ pháp luật: {res['clause']}"
                )
                
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n\n".join(out) if len(out) > 1 else "Không phát hiện quy định chồng chéo chéo với các văn bản còn hiệu lực khác cùng ngành."
                    }
                ]
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Lỗi rà soát chồng chéo: {str(e)}"}]}
            
    return {"content": [{"type": "text", "text": f"Lỗi: Không tìm thấy tool '{name}'."}]}

def main():
    log("Khởi động dataluatvn MCP Server...")
    
    # Đọc tuần tự từ stdin
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")
            
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "dataluatvn-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
                send_response(res)
                
            elif method == "notifications/initialized":
                log("Khởi tạo hoàn tất. Client đã sẵn sàng kết nối.")
                
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "search_laws",
                                "description": "Tìm kiếm văn bản pháp luật Việt Nam bằng từ khóa (FTS) và các bộ lọc.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "q": {"type": "string", "description": "Từ khóa tìm kiếm (ví dụ: đất đai, thuế)"},
                                        "loai_van_ban": {"type": "string", "description": "Lọc theo loại văn bản (ví dụ: Luật, Nghị định, Thông tư)"},
                                        "tinh_trang": {"type": "string", "description": "Lọc theo tình trạng hiệu lực (ví dụ: Còn hiệu lực)"},
                                        "limit": {"type": "integer", "description": "Giới hạn số kết quả trả về (mặc định: 5)"}
                                    },
                                    "required": ["q"]
                                }
                            },
                            {
                                "name": "get_document",
                                "description": "Lấy chi tiết toàn văn (văn bản thô sạch) và metadata của văn bản bằng ID hoặc Số ký hiệu.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer", "description": "ID văn bản trong database (ví dụ: 96122)"},
                                        "so_ky_hieu": {"type": "string", "description": "Số ký hiệu văn bản (ví dụ: 80/2015/QH13)"}
                                    }
                                }
                            },
                            {
                                "name": "get_law_lineage",
                                "description": "Lấy sơ đồ cây phả hệ pháp luật (văn bản căn cứ, hướng dẫn thi hành, sửa đổi) của văn bản.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer", "description": "ID văn bản"}
                                    },
                                    "required": ["id"]
                                }
                            },
                            {
                                "name": "check_law_overlaps",
                                "description": "Kiểm tra sự chồng chéo, xung đột quy định và đề xuất áp dụng theo Điều 156 Luật ban hành VBQPPL.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer", "description": "ID văn bản"}
                                    },
                                    "required": ["id"]
                                }
                            }
                        ]
                    }
                }
                send_response(res)
                
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {})
                
                result = handle_tool_call(name, arguments)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
                send_response(res)
                
            else:
                if req_id is not None:
                    send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Phương thức không hợp lệ: {method}"
                        }
                    })
        except Exception as e:
            log(f"Lỗi phân tích cú pháp yêu cầu: {str(e)}")

if __name__ == "__main__":
    main()
