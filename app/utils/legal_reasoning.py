#!/usr/bin/env python3
"""
app/utils/legal_reasoning.py
==============================
Module IRAC Reasoning Engine — Phương pháp luận pháp lý cấp Thạc sĩ Luật.

Cung cấp:
1. IRAC Framework (Issue → Rule → Application → Conclusion)
2. Tam đoạn luận pháp lý (Legal Syllogism)  
3. 4 Phương pháp diễn giải luật (Textual, Systematic, Teleological, Historical)
4. Conflict resolution giữa các văn bản pháp luật

Module này KHÔNG gọi LLM — nó tạo ra structured prompts/instructions để inject vào
system prompt của LLM, giúp LLM tư duy theo phương pháp luận pháp lý chuẩn mực.
"""

import re
from typing import Dict, Any, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════
# 1. IRAC FRAMEWORK
# ══════════════════════════════════════════════════════════════

IRAC_SYSTEM_INSTRUCTION = """
## PHƯƠNG PHÁP PHÂN TÍCH PHÁP LÝ IRAC

Khi phân tích bất kỳ vấn đề pháp lý nào, bạn PHẢI tuân thủ khung phân tích IRAC sau đây:

### 🔍 I — ISSUE (Vấn đề pháp lý)
- Xác định chính xác vấn đề pháp lý trọng tâm cần giải quyết
- Phân biệt vấn đề chính và vấn đề phụ
- Đặt câu hỏi pháp lý dưới dạng: "Liệu [hành vi/tình huống] có [vi phạm/phù hợp với] [quy định pháp luật] hay không?"

### 📜 R — RULE (Quy phạm pháp luật áp dụng)
- Xác định VBQPPL áp dụng (Luật nội dung + Luật hình thức/tố tụng)
- Trích dẫn chính xác Điều, Khoản, Điểm
- Nếu có nhiều VBQPPL cùng điều chỉnh → áp dụng nguyên tắc ưu tiên:
  (1) Văn bản có hiệu lực pháp lý cao hơn
  (2) Văn bản chuyên ngành ưu tiên hơn văn bản chung
  (3) Văn bản ban hành sau ưu tiên hơn văn bản trước (cùng cơ quan)
- Nếu có Án lệ liên quan → trích dẫn Án lệ số mấy, Tòa nào ban hành

### ⚖️ A — APPLICATION (Áp dụng quy phạm vào tình tiết thực tế)
- Sử dụng TAM ĐOẠN LUẬN PHÁP LÝ:
  * Đại tiền đề: Quy phạm pháp luật (Rule)
  * Tiểu tiền đề: Tình tiết thực tế (Fact)
  * Kết luận: Hệ quả pháp lý
- Đối chiếu từng yếu tố cấu thành của quy phạm với tình tiết thực tế
- Nếu là vụ án hình sự → phân tích 4 yếu tố cấu thành tội phạm:
  (1) Chủ thể: Ai thực hiện? Có năng lực TNHS không?
  (2) Khách thể: Quan hệ xã hội nào bị xâm hại?
  (3) Mặt khách quan: Hành vi, hậu quả, mối quan hệ nhân quả
  (4) Mặt chủ quan: Lỗi cố ý hay vô ý? Động cơ, mục đích?

### ✅ C — CONCLUSION (Kết luận pháp lý)
- Kết luận rõ ràng, dứt khoát: Đúng/Sai, Hợp pháp/Trái luật, Có tội/Không có tội
- Nêu hệ quả pháp lý cụ thể: mức phạt, thời hạn, quyền và nghĩa vụ
- Nếu có nhiều phương án → đánh giá ưu/nhược điểm từng phương án
"""

# ══════════════════════════════════════════════════════════════
# 2. 4 PHƯƠNG PHÁP DIỄN GIẢI LUẬT
# ══════════════════════════════════════════════════════════════

INTERPRETATION_METHODS = {
    "textual": {
        "name": "Diễn giải theo nghĩa đen (Textual Interpretation)",
        "description": "Áp dụng đúng từ ngữ, câu chữ của điều luật. Đây là phương pháp ưu tiên hàng đầu.",
        "when_to_use": "Khi quy định pháp luật rõ ràng, cụ thể, không mơ hồ.",
        "instruction": "Đọc và áp dụng ĐÚNG từ ngữ trong điều luật. Không mở rộng hay thu hẹp phạm vi nghĩa của từ ngữ."
    },
    "systematic": {
        "name": "Diễn giải hệ thống (Systematic Interpretation)",
        "description": "Đặt điều luật trong bối cảnh toàn bộ hệ thống pháp luật để hiểu nghĩa.",
        "when_to_use": "Khi điều luật liên quan đến nhiều VBQPPL khác nhau, hoặc khi cần xác định mối quan hệ giữa luật chung và luật chuyên ngành.",
        "instruction": "Phân tích điều luật trong mối liên hệ với: (1) Các điều khoản khác trong cùng VBQPPL, (2) Các VBQPPL liên quan, (3) Nguyên tắc chung của hệ thống pháp luật."
    },
    "teleological": {
        "name": "Diễn giải theo mục đích (Teleological Interpretation)",
        "description": "Diễn giải dựa trên mục đích, ý chí của nhà làm luật khi ban hành.",
        "when_to_use": "Khi từ ngữ điều luật mơ hồ, hoặc khi áp dụng theo nghĩa đen dẫn đến kết quả bất hợp lý.",
        "instruction": "Xác định: (1) Mục đích ban hành VBQPPL (thường ghi ở phần Mở đầu/Lời nói đầu), (2) Đối tượng mà nhà làm luật muốn bảo vệ, (3) Hệ quả thực tế nếu áp dụng theo nghĩa đen vs theo mục đích."
    },
    "historical": {
        "name": "Diễn giải lịch sử (Historical Interpretation)",
        "description": "Diễn giải dựa trên lịch sử lập pháp, quá trình xây dựng và sửa đổi VBQPPL.",
        "when_to_use": "Khi VBQPPL đã được sửa đổi nhiều lần, hoặc khi cần hiểu lý do nhà làm luật thay đổi quy định.",
        "instruction": "So sánh: (1) Quy định hiện hành với quy định cũ, (2) Tờ trình/Báo cáo thuyết minh của cơ quan soạn thảo, (3) Biên bản thảo luận tại Quốc hội (nếu có)."
    }
}

# ══════════════════════════════════════════════════════════════
# 3. CẤU THÀNH TỘI PHẠM (Dùng cho phân tích hình sự)
# ══════════════════════════════════════════════════════════════

CRIME_ELEMENTS_INSTRUCTION = """
## PHÂN TÍCH 4 YẾU TỐ CẤU THÀNH TỘI PHẠM (BLHS 2015)

### 1. CHỦ THỂ (Subject)
- Là ai? (cá nhân / pháp nhân thương mại)
- Có đủ tuổi chịu TNHS không? (Điều 12 BLHS: ≥16 tuổi mọi tội; ≥14 tuổi tội rất nghiêm trọng/đặc biệt nghiêm trọng cố ý)
- Có năng lực TNHS không? (Điều 21 BLHS: không mắc bệnh tâm thần)
- Có chủ thể đặc biệt không? (công chức, người có chức vụ, quân nhân...)

### 2. KHÁCH THỂ (Object)
- Quan hệ xã hội nào bị xâm hại?
  * Tính mạng, sức khỏe → Chương XIV BLHS
  * Quyền sở hữu tài sản → Chương XVI BLHS
  * Trật tự quản lý kinh tế → Chương XVIII BLHS
  * An ninh quốc gia → Chương XIII BLHS

### 3. MẶT KHÁCH QUAN (Objective Element)
- Hành vi nguy hiểm cho xã hội: Hành động hay không hành động?
- Hậu quả: Thiệt hại gì đã xảy ra? (chết người, tổn hại sức khỏe, thiệt hại tài sản)
- Mối quan hệ nhân quả: Hành vi → Hậu quả có mối liên hệ trực tiếp không?
- Công cụ, phương tiện phạm tội
- Thời gian, địa điểm, hoàn cảnh phạm tội

### 4. MẶT CHỦ QUAN (Subjective Element)  
- Lỗi CỐ Ý (Điều 10 BLHS):
  * Cố ý trực tiếp: Nhận thức rõ hành vi nguy hiểm + mong muốn hậu quả xảy ra
  * Cố ý gián tiếp: Nhận thức rõ hành vi nguy hiểm + để mặc hậu quả xảy ra
- Lỗi VÔ Ý (Điều 11 BLHS):
  * Vô ý vì quá tự tin: Thấy trước hậu quả nhưng tin sẽ ngăn ngừa được
  * Vô ý vì cẩu thả: Không thấy trước hậu quả dù phải thấy trước và có thể thấy trước
- Động cơ, mục đích phạm tội (ảnh hưởng đến định tội và lượng hình)
"""

# ══════════════════════════════════════════════════════════════
# 4. FUNCTIONS
# ══════════════════════════════════════════════════════════════

def detect_legal_complexity(query: str) -> str:
    """
    Phân loại mức độ phức tạp pháp lý của câu hỏi.
    Returns: 'simple', 'moderate', 'complex', 'adversarial'
    """
    q_lower = query.lower()
    
    # Adversarial: Yêu cầu phân tích đa chiều
    adversarial_patterns = [
        r"(phân tích.*đa chiều|cả hai bên|đúng hay sai|hợp pháp hay không)",
        r"(ai đúng ai sai|bên nào thắng|khả năng thắng kiện)",
        r"(tranh luận|phản bác|biện hộ|bào chữa cho|buộc tội)",
    ]
    for p in adversarial_patterns:
        if re.search(p, q_lower):
            return "adversarial"
    
    # Complex: Nhiều vấn đề pháp lý đan xen
    complex_patterns = [
        r"(vừa.*vừa|đồng thời|ngoài ra|mặt khác)",
        r"(tranh chấp.*thừa kế.*đất đai|hình sự.*dân sự)",
        r"(xung đột.*pháp luật|mâu thuẫn.*quy định)",
        r"(so sánh|khác nhau|giống nhau|đối chiếu)",
    ]
    for p in complex_patterns:
        if re.search(p, q_lower):
            return "complex"
    
    # Moderate: Cần phân tích chuyên sâu
    moderate_patterns = [
        r"(cấu thành tội phạm|tình tiết giảm nhẹ|tình tiết tăng nặng)",
        r"(thẩm quyền.*tòa án|quyền.*bào chữa)",
        r"(bồi thường thiệt hại|trách nhiệm.*hợp đồng)",
        r"(có vi phạm.*không|có phải.*tội|có được.*không)",
    ]
    for p in moderate_patterns:
        if re.search(p, q_lower):
            return "moderate"
    
    return "simple"


def get_irac_instruction(query: str, complexity: Optional[str] = None) -> str:
    """
    Trả về IRAC instruction phù hợp với mức độ phức tạp của câu hỏi.
    Instruction này sẽ được inject vào system prompt của LLM.
    """
    if complexity is None:
        complexity = detect_legal_complexity(query)
    
    if complexity == "simple":
        return ""  # Câu hỏi đơn giản không cần IRAC
    
    q_lower = query.lower()
    
    # Câu hỏi hình sự → thêm phân tích cấu thành tội phạm
    is_criminal = any(k in q_lower for k in [
        "tội", "hình sự", "bắt giam", "truy tố", "khởi tố",
        "giết người", "cướp", "trộm cắp", "lừa đảo", "ma túy",
        "hình phạt", "tù", "án tử", "án treo"
    ])
    
    instruction = IRAC_SYSTEM_INSTRUCTION
    
    if is_criminal:
        instruction += "\n" + CRIME_ELEMENTS_INSTRUCTION
    
    if complexity == "adversarial":
        instruction += """
## LẬP LUẬN ĐA CHIỀU ĐỐI KHÁNG

Khi phân tích vấn đề này, bạn PHẢI trình bày ĐỒNG THỜI 3 góc nhìn:

### 👨‍⚖️ GÓC NHÌN BẢO VỆ (Luật sư bào chữa)
- Tìm mọi tình tiết CÓ LỢI
- Tìm mọi sơ hở tố tụng
- Viện dẫn tình tiết giảm nhẹ

### ⚖️ GÓC NHÌN BUỘC TỘI (Kiểm sát viên)
- Tìm mọi chứng cứ BẤT LỢI
- Phân tích cấu thành tội phạm đầy đủ
- Viện dẫn tình tiết tăng nặng

### 🏛️ GÓC NHÌN PHÁN QUYẾT (Thẩm phán)
- Cân nhắc CÔNG BẰNG cả hai bên
- Áp dụng Án lệ nếu có tình tiết tương tự
- Ra kết luận thấu tình đạt lý
"""
    
    return instruction


def select_interpretation_method(query: str, has_ambiguity: bool = False, has_multiple_laws: bool = False) -> str:
    """
    Chọn phương pháp diễn giải luật phù hợp và trả về instruction tương ứng.
    """
    methods_to_use = []
    
    q_lower = query.lower()
    
    # Always start with textual
    methods_to_use.append("textual")
    
    # If multiple laws involved
    if has_multiple_laws or any(k in q_lower for k in ["nhiều luật", "luật nào áp dụng", "xung đột", "mâu thuẫn"]):
        methods_to_use.append("systematic")
    
    # If ambiguous or "spirit of the law" question
    if has_ambiguity or any(k in q_lower for k in ["tinh thần", "mục đích", "ý nghĩa", "tại sao", "vì sao"]):
        methods_to_use.append("teleological")
    
    # If comparing old vs new law
    if any(k in q_lower for k in ["so sánh", "luật cũ", "luật mới", "sửa đổi", "trước đây", "thay đổi"]):
        methods_to_use.append("historical")
    
    if len(methods_to_use) <= 1:
        return ""  # Textual only — no special instruction needed
    
    instruction = "\n## PHƯƠNG PHÁP DIỄN GIẢI LUẬT ÁP DỤNG\n\n"
    for method_key in methods_to_use:
        m = INTERPRETATION_METHODS[method_key]
        instruction += f"### {m['name']}\n{m['instruction']}\n\n"
    
    return instruction


def build_reasoning_prompt(
    query: str,
    role: Optional[str] = None,
    retrieved_docs: Optional[List[Dict]] = None,
    precedents: Optional[List[Dict]] = None,
) -> str:
    """
    Xây dựng reasoning instruction tổng hợp để inject vào system prompt.
    Kết hợp IRAC + Phương pháp diễn giải + Phân tích cấu thành (nếu hình sự).
    
    Args:
        query: Câu hỏi của người dùng
        role: Vai trò tư pháp hiện tại (lawyer, prosecutor, judge, enforcement, investigator)
        retrieved_docs: Danh sách VBQPPL đã truy xuất
        precedents: Danh sách Án lệ liên quan
    
    Returns:
        reasoning_instruction: Chuỗi instruction inject vào system prompt
    """
    complexity = detect_legal_complexity(query)
    
    parts = []
    
    # 1. IRAC Framework (nếu câu hỏi moderate+)
    irac = get_irac_instruction(query, complexity)
    if irac:
        parts.append(irac)
    
    # 2. Phương pháp diễn giải (nếu cần)
    has_multiple_laws = retrieved_docs and len(retrieved_docs) > 3
    interp = select_interpretation_method(query, has_ambiguity=False, has_multiple_laws=has_multiple_laws)
    if interp:
        parts.append(interp)
    
    # 3. Hướng dẫn áp dụng Án lệ (nếu có)
    if precedents:
        precedent_instruction = "\n## ÁP DỤNG ÁN LỆ\n\n"
        precedent_instruction += "Các Án lệ/Bản án liên quan đã được truy xuất. Khi phân tích, hãy:\n"
        precedent_instruction += "1. So sánh TÌNH TIẾT THỰC TẾ của vụ việc hiện tại với tình tiết trong Án lệ\n"
        precedent_instruction += "2. Nếu tình tiết TƯƠNG TỰ → áp dụng nguyên tắc/quyết định trong Án lệ\n"
        precedent_instruction += "3. Nếu tình tiết KHÁC BIỆT → giải thích điểm khác biệt (distinguishing)\n"
        precedent_instruction += "4. Trích dẫn rõ: Án lệ số mấy, Tòa nào, Năm nào\n"
        parts.append(precedent_instruction)
    
    # 4. Hướng dẫn theo vai trò (nếu có)
    if role and role != "default":
        role_instructions = {
            "lawyer": """
## TƯ DUY CHIẾN LƯỢC LUẬT SƯ BÀO CHỮA
- Ưu tiên tìm mọi tình tiết CÓ LỢI cho thân chủ
- Phát hiện sơ hở tố tụng, vi phạm thủ tục của cơ quan tiến hành tố tụng
- Viện dẫn tình tiết giảm nhẹ TNHS (Điều 51 BLHS 2015) hoặc giảm mức bồi thường
- Đề xuất phương án phòng vệ pháp lý tối ưu
- Phân tích khả năng kháng cáo nếu bản án bất lợi
""",
            "prosecutor": """
## TƯ DUY KIỂM SÁT VIÊN THỰC HÀNH QUYỀN CÔNG TỐ
- Phân tích chứng cứ BUỘC TỘI theo nguyên tắc: chứng cứ phải hợp pháp, xác thực, liên quan
- Kiểm tra tính đầy đủ của 4 yếu tố cấu thành tội phạm
- Viện dẫn tình tiết tăng nặng TNHS (Điều 52 BLHS 2015) nếu có
- Đánh giá: Đủ căn cứ truy tố hay phải trả hồ sơ điều tra bổ sung?
- Kiểm sát hoạt động tư pháp: Hoạt động điều tra có đúng pháp luật không?
""",
            "judge": """
## TƯ DUY THẨM PHÁN CHỦ TỌA PHIÊN TÒA
- KHÁCH QUAN tuyệt đối: Cân nhắc bình đẳng chứng cứ các bên
- Đánh giá tính hợp pháp và giá trị chứng minh của từng chứng cứ
- Áp dụng Án lệ nếu có tình tiết tương tự (theo Nghị quyết 04/2019/NQ-HĐTP)
- Quyết định hình phạt theo nguyên tắc cá thể hóa hình phạt
- Bản án phải "thấu tình đạt lý" — không chỉ đúng pháp luật mà còn phù hợp thực tiễn
""",
            "investigator": """
## TƯ DUY ĐIỀU TRA VIÊN HÌNH SỰ  
- Thu thập chứng cứ theo trình tự pháp luật (bất kỳ vi phạm thủ tục nào → chứng cứ bị loại bỏ)
- Khám nghiệm hiện trường: Bảo vệ hiện trường, ghi nhận vết tích, thu giữ vật chứng
- Lấy lời khai: Đảm bảo quyền của người bị tạm giữ/bị can (quyền có Luật sư, quyền im lặng)
- Mục tiêu: Làm rõ SỰ THẬT khách quan, KHÔNG bỏ sót tội phạm, KHÔNG làm oan người vô tội
""",
            "enforcement": """
## TƯ DUY CHẤP HÀNH VIÊN THI HÀNH ÁN DÂN SỰ
- Kiểm tra tính hợp pháp của Bản án/Quyết định cần thi hành
- Xác minh điều kiện thi hành án: Người phải THA có tài sản/thu nhập để thi hành không?
- Lựa chọn biện pháp cưỡng chế phù hợp và theo đúng trình tự pháp luật:
  (1) Khấu trừ tài khoản → (2) Kê biên tài sản → (3) Bán đấu giá
- Bảo vệ quyền lợi người được THA nhưng cũng bảo đảm quyền cơ bản của người phải THA
"""
        }
        if role in role_instructions:
            parts.append(role_instructions[role])
    
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════
# 5. QUICK ACCESS FUNCTIONS
# ══════════════════════════════════════════════════════════════

def get_complexity_label(query: str) -> str:
    """Trả về nhãn mức độ phức tạp bằng tiếng Việt."""
    mapping = {
        "simple": "Đơn giản",
        "moderate": "Trung bình",
        "complex": "Phức tạp",
        "adversarial": "Đa chiều đối kháng"
    }
    return mapping.get(detect_legal_complexity(query), "Đơn giản")


if __name__ == "__main__":
    # Test
    test_queries = [
        "Mức phạt vượt đèn đỏ là bao nhiêu?",
        "Hành vi A có cấu thành tội cướp tài sản không?",
        "Vừa tranh chấp đất đai vừa kiện đòi thừa kế, ngoài ra còn yêu cầu bồi thường thiệt hại — tôi nên làm gì?",
        "Phân tích đa chiều: bên nào thắng trong vụ kiện hợp đồng thương mại?",
    ]
    
    for q in test_queries:
        complexity = detect_legal_complexity(q)
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print(f"Complexity: {complexity} ({get_complexity_label(q)})")
        instruction = build_reasoning_prompt(q, role="judge")
        print(f"Instruction length: {len(instruction)} chars")
        if instruction:
            print(f"First 200 chars: {instruction[:200]}...")
