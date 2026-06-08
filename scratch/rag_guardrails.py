"""
rag_guardrails.py — Giải pháp toàn diện phòng chống ảo giác (hallucination) 
và xác thực trích dẫn (citation validation) cho Chatbot Pháp Luật RAG.

Tính năng:
  1. Retrieve Context: Truy vấn và làm sạch nội dung văn bản luật còn hiệu lực.
  2. Strict Prompting: Tạo prompt ràng buộc chặt chẽ luật trích dẫn.
  3. LLM API Settings: Cấu hình an toàn (temperature=0.0, top_p=0.1).
  4. Post-processing Validation: Sử dụng Regex để đối soát chéo số hiệu văn bản 
     trong câu trả lời của LLM với danh sách văn bản thực tế được truyền vào.
"""
import sqlite3
import re
import os
from typing import List, Dict, Tuple, Optional
from bs4 import BeautifulSoup

class RAGGuardrails:
    def __init__(self, db_path: str = "vietnamese_legal_documents.db", content_db_path: str = "content_store.db"):
        self.db_path = db_path
        self.content_db_path = content_db_path

    def _clean_html(self, html_content: str) -> str:
        """Lọc bỏ các thẻ HTML để tối ưu hóa context nạp vào LLM."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        # Loại bỏ các tag không cần thiết
        for tag in soup(["script", "style", "iframe"]):
            tag.decompose()
        # Lấy text sạch
        text = soup.get_text(separator="\n")
        # Chuẩn hóa khoảng trắng
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def retrieve_context(self, query: str, limit: int = 4) -> List[Dict]:
        """
        1. TRUY VẤN VÀ LÀM SẠCH DỮ LIỆU (RETRIEVAL)
        Tìm kiếm văn bản liên quan có FTS5, lọc bỏ các văn bản hết hiệu lực.
        """
        if not os.path.exists(self.db_path):
            print(f"❌ Database chính {self.db_path} không tồn tại!")
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Tìm kiếm bằng FTS5
        # Chỉ lấy những văn bản có trạng thái "Còn hiệu lực" hoặc "Chưa có hiệu lực"
        sql = """
            SELECT d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.loai_van_ban, d.tinh_trang_hieu_luc
            FROM documents d
            JOIN documents_fts fts ON d.id = fts.rowid
            WHERE documents_fts MATCH ? 
              AND d.tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Chưa có hiệu lực')
            ORDER BY fts.rank
            LIMIT ?
        """
        # Escape truy vấn MATCH
        escaped_q = query.replace('"', '""')
        cursor.execute(sql, (f'"{escaped_q}"', limit))
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            doc = dict(r)
            # Lấy content_html từ content_store.db
            doc["content_text"] = ""
            if os.path.exists(self.content_db_path):
                try:
                    conn_c = sqlite3.connect(self.content_db_path)
                    cursor_c = conn_c.cursor()
                    cursor_c.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (doc["id"],))
                    row_c = cursor_c.fetchone()
                    if row_c and row_c[0]:
                        # Làm sạch HTML thành text thường
                        doc["content_text"] = self._clean_html(row_c[0])
                    conn_c.close()
                except Exception as e:
                    print(f"⚠️ Lỗi đọc content_store.db: {e}")
            results.append(doc)

        conn.close()
        return results

    def build_strict_prompt(self, query: str, context_docs: List[Dict]) -> str:
        """
        2. RÀNG BUỘC PROMPT (STRICT PROMPTING)
        Tạo prompt ép LLM chỉ trả lời dựa trên context được truyền vào.
        """
        # Xây dựng chuỗi văn bản ngữ cảnh
        context_str = ""
        for i, doc in enumerate(context_docs, 1):
            so_hieu = doc.get("so_ky_hieu") or "Không có số hiệu"
            title = doc.get("title") or "Không có tiêu đề"
            content = doc.get("content_text") or "Nội dung đang được cập nhật..."
            # Cắt bớt content nếu quá dài (> 3000 từ) để tránh tràn cửa sổ ngữ cảnh
            if len(content) > 12000:
                content = content[:12000] + "\n...[Cắt ngắn bớt nội dung dài]..."
                
            context_str += f"=== VĂN BẢN [{i}]: {title} ===\n"
            context_str += f"- Số ký hiệu: {so_hieu}\n"
            context_str += f"- Tình trạng: {doc.get('tinh_trang_hieu_luc')}\n"
            context_str += f"- Nội dung:\n{content}\n\n"

        prompt = f"""Bạn là một Trợ lý ảo tư vấn Luật Việt Nam chuyên nghiệp, chính xác và trung thực tuyệt đối.
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng bằng cách SỬ DỤNG DUY NHẤT các văn bản pháp luật được cung cấp dưới đây trong phần "NGỮ CẢNH PHÁP LUẬT".

---
NGỮ CẢNH PHÁP LUẬT:
{context_str}
---

YÊU CẦU NGHIÊM NGẶT ĐỂ TRÁNH ẢO GIÁC (BỊA LUẬT):
1. Bạn chỉ được phép đưa ra thông tin có bằng chứng trực tiếp nằm trong "NGỮ CẢNH PHÁP LUẬT". Tuyệt đối không tự suy luận, tự bổ sung hoặc lấy kiến thức có sẵn từ trước của bạn để bịa ra điều luật.
2. Nếu câu hỏi của người dùng KHÔNG CÓ thông tin trả lời trong ngữ cảnh pháp luật được cung cấp, bạn bắt buộc phải trả lời nguyên văn câu sau:
   "Tôi xin lỗi, thông tin pháp luật hiện tại trong cơ sở dữ liệu của tôi không đủ để trả lời chính xác câu hỏi này."
   Sau đó bạn có thể gợi ý người dùng các câu hỏi liên quan khác hoặc đề xuất tham vấn ý kiến luật sư.
3. Khi đưa ra câu trả lời, bạn phải viện dẫn chính xác số hiệu văn bản pháp lý (Ví dụ: "Luật số 31/2024/QH15" hoặc "Nghị định số 12/2024/NĐ-CP") và điều khoản cụ thể (Điều mấy, Khoản mấy).

CÂU HỎI CỦA NGƯỜI DÙNG: {query}
CÂU TRẢ LỜI CỦA BẠN:"""

        return prompt

    def validate_citations(self, response_text: str, context_docs: List[Dict]) -> Tuple[bool, str, List[str]]:
        """
        3. KIỂM TRA CHÉO TRÍCH DẪN (POST-PROCESSING CITATION VALIDATION)
        Dùng Regex bóc tách tất cả số ký hiệu văn bản trong câu trả lời của LLM, 
        sau đó đối chiếu với các số ký hiệu thực tế được truyền vào.
        
        Trả về: 
          - is_safe (bool): True nếu an toàn, False nếu bị ảo giác (bịa luật).
          - log_message (str): Thông tin chi tiết kết quả kiểm tra.
          - hallucinated_citations (list): Danh sách các số hiệu tự bịa.
        """
        # Regex tìm số hiệu văn bản (Ví dụ: 12/2024/NĐ-CP, 31/2024/QH15)
        citation_pattern = r'(\d+/\d{4}/[A-ZĐa-zđ\-]+)'
        
        # Lấy tất cả số hiệu từ câu trả lời của LLM
        llm_citations = set(re.findall(citation_pattern, response_text))
        
        # Lấy tất cả số hiệu thực tế từ Context được nạp
        valid_citations = set()
        for doc in context_docs:
            so_hieu = doc.get("so_ky_hieu")
            if so_hieu:
                # Chuẩn hóa khoảng trắng
                valid_citations.add(so_hieu.strip())
                
        # Tìm những số hiệu LLM đưa ra nhưng không có trong Context thực tế
        hallucinated = []
        for cit in llm_citations:
            # So khớp tương đối để tránh lệch dấu cách hoặc ký tự viết hoa/thường
            matched = False
            for v_cit in valid_citations:
                if cit.lower().replace(" ", "") == v_cit.lower().replace(" ", ""):
                    matched = True
                    break
            if not matched:
                hallucinated.append(cit)

        if hallucinated:
            msg = f"⚠️ PHÁT HIỆN ẢO GIÁC: Chatbot đã tự bịa ra các văn bản pháp lý không có trong dữ liệu truyền vào: {hallucinated}"
            return False, msg, hallucinated
            
        msg = f"✅ AN TOÀN: Tất cả trích dẫn trong câu trả lời ({list(llm_citations)}) đều hợp lệ và khớp với ngữ cảnh."
        return True, msg, []

    def run_safe_rag_pipeline(self, query: str, call_llm_fn) -> Dict:
        """
        VẬN HÀNH PIPELINE RAG AN TOÀN TOÀN DIỆN
        
        Arguments:
          - query (str): Câu hỏi người dùng.
          - call_llm_fn: Hàm callback để gọi LLM (OpenAI/Gemini) nhận vào Prompt và trả về Text.
            Hàm này phải cấu hình temperature=0.0 khi gọi API.
        """
        print(f"\n🔍 Bước 1: Tìm kiếm tài liệu luật liên quan cho câu hỏi: '{query}'...")
        context_docs = self.retrieve_context(query, limit=4)
        
        if not context_docs:
            return {
                "safe": True,
                "response": "Tôi xin lỗi, thông tin pháp luật hiện tại trong cơ sở dữ liệu của tôi không đủ để trả lời chính xác câu hỏi này.",
                "citations": [],
                "validation_message": "Không tìm thấy văn bản pháp lý nào khớp trong DB chính."
            }
            
        print(f"   -> Tìm thấy {len(context_docs)} văn bản luật còn hiệu lực.")
        
        print("\n📝 Bước 2: Tạo strict prompt ràng buộc...")
        prompt = self.build_strict_prompt(query, context_docs)
        
        print("\n🤖 Bước 3: Gửi prompt lên LLM (Yêu cầu cấu hình temperature=0.0)...")
        # Gọi callback LLM
        response_text = call_llm_fn(prompt)
        
        print("\n🛡️ Bước 4: Chạy thuật toán đối soát chéo trích dẫn (Citation Guardrail)...")
        is_safe, val_msg, hallucinated = self.validate_citations(response_text, context_docs)
        
        # Nếu phát hiện bịa luật, kích hoạt cơ chế Fallback để bảo đảm an toàn pháp lý
        final_response = response_text
        if not is_safe:
            print(val_msg)
            final_response = (
                "Tôi xin lỗi, thông tin pháp luật hiện tại trong cơ sở dữ liệu của tôi không đủ để trả lời chính xác câu hỏi này.\n"
                f"[Hệ thống chặn câu trả lời do LLM tự trích dẫn sai nguồn luật: {hallucinated}]"
            )
        else:
            print(val_msg)
            
        return {
            "safe": is_safe,
            "response": final_response,
            "citations": [doc.get("so_ky_hieu") for doc in context_docs if doc.get("so_ky_hieu")],
            "validation_message": val_msg
        }

# ==========================================
# ĐOẠN CODE CHẠY THỬ NGHIỆM (MOCK TEST)
# ==========================================
if __name__ == "__main__":
    guard = RAGGuardrails()
    
    # Giả lập hàm gọi LLM bị ảo giác (bịa ra luật 99/2026/NĐ-CP không có thực)
    def mock_hallucinated_llm(prompt):
        return (
            "Dựa trên các quy định được cung cấp, người sử dụng đất có các quyền chung được quy định tại Điều 26.\n"
            "Ngoài ra, theo Nghị định số 99/2026/NĐ-CP ban hành sau này, người dân còn được miễn thuế đất đai."
        )

    # Giả lập hàm gọi LLM an toàn
    def mock_safe_llm(prompt):
        return (
            "Theo Điều 26 Luật Đất đai (số ký hiệu: 31/2024/QH15) trong ngữ cảnh,\n"
            "người sử dụng đất có các quyền chung bao gồm: Được cấp Giấy chứng nhận quyền sử dụng đất,\n"
            "và hưởng thành quả lao động, kết quả đầu tư trên đất."
        )

    print("--- CHẠY THỬ NGHIỆM 1: PHÁT HIỆN LLM BỊA LUẬT ---")
    # Giả lập context chứa văn bản thực tế
    fake_context = [
        {"id": 1, "so_ky_hieu": "31/2024/QH15", "title": "Luật Đất Đai 2024", "tinh_trang_hieu_luc": "Còn hiệu lực"}
    ]
    
    # Chạy thử validate trích dẫn
    response = mock_hallucinated_llm("Prompt")
    is_safe, msg, hallucinated = guard.validate_citations(response, fake_context)
    print("Câu trả lời của LLM:")
    print(f"  > '{response}'")
    print(f"Kết quả kiểm tra: Safe={is_safe}")
    print(f"Thông điệp: {msg}\n")
    
    print("--- CHẠY THỬ NGHIỆM 2: LLM TRẢ LỜI AN TOÀN ---")
    response_safe = mock_safe_llm("Prompt")
    is_safe, msg, hallucinated = guard.validate_citations(response_safe, fake_context)
    print("Câu trả lời của LLM:")
    print(f"  > '{response_safe}'")
    print(f"Kết quả kiểm tra: Safe={is_safe}")
    print(f"Thông điệp: {msg}\n")
