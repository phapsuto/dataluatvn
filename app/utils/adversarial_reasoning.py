#!/usr/bin/env python3
"""
app/utils/adversarial_reasoning.py
====================================
Module Lập luận Đa chiều Đối kháng — Tư duy cấp Tiến sĩ Luật.

Khi gặp vấn đề pháp lý phức tạp, module này hướng dẫn LLM tự động phân tích
đồng thời từ 3 góc nhìn đối kháng:

1. 👨‍⚖️ LUẬT SƯ BÀO CHỮA → Tìm mọi lý do có lợi
2. ⚖️ KIỂM SÁT VIÊN → Tìm mọi căn cứ bất lợi  
3. 🏛️ THẨM PHÁN → Cân nhắc cả hai, ra phán quyết công bằng

Module này tạo ra structured instructions inject vào system prompt,
KHÔNG gọi LLM trực tiếp.
"""

import re
from typing import Optional, Dict, Any


def should_use_adversarial(query: str) -> bool:
    """
    Phát hiện câu hỏi cần phân tích đa chiều đối kháng.
    Returns True khi query có dấu hiệu tranh chấp, xung đột, hoặc yêu cầu đánh giá đa chiều.
    """
    q_lower = query.lower()
    
    patterns = [
        # Yêu cầu trực tiếp
        r"(phân tích.*đa chiều|cả hai bên|đúng hay sai|hợp pháp hay không)",
        r"(ai đúng ai sai|bên nào thắng|khả năng thắng kiện)",
        r"(tranh luận|phản bác|biện hộ|bào chữa cho|buộc tội)",
        r"(vai.*luật sư.*kiểm sát|vai.*thẩm phán)",
        
        # Tranh chấp 2 bên
        r"(bên a.*bên b|nguyên đơn.*bị đơn|bên mua.*bên bán)",
        r"(tranh chấp|khiếu nại|kiện|tố cáo|khởi kiện)",
        r"(mâu thuẫn|xung đột|bất đồng|không thống nhất)",
        
        # Câu hỏi mở về tội phạm phức tạp
        r"(có phạm tội.*không|có vi phạm.*không|có trái luật.*không)",
        r"(cấu thành tội.*hay.*không|đủ yếu tố.*không)",
    ]
    
    for p in patterns:
        if re.search(p, q_lower):
            return True
    
    return False


def build_adversarial_instruction(query: str, context_hint: Optional[str] = None) -> str:
    """
    Tạo instruction lập luận đa chiều đối kháng cho LLM.
    
    Args:
        query: Câu hỏi người dùng
        context_hint: Gợi ý bối cảnh (hình sự, dân sự, lao động...)
    
    Returns:
        Instruction string để inject vào system prompt
    """
    q_lower = query.lower()
    
    # Detect if criminal or civil
    is_criminal = any(k in q_lower for k in [
        "tội", "hình sự", "truy tố", "bắt giam", "khởi tố",
        "giết", "cướp", "trộm", "lừa đảo", "ma túy", "tham nhũng"
    ])
    
    if is_criminal:
        return _build_criminal_adversarial(query)
    else:
        return _build_civil_adversarial(query)


def _build_criminal_adversarial(query: str) -> str:
    """Instruction đối kháng cho vụ án hình sự."""
    return """
## ⚔️ PHÂN TÍCH ĐA CHIỀU ĐỐI KHÁNG — VỤ ÁN HÌNH SỰ

Bạn PHẢI phân tích vấn đề pháp lý này đồng thời từ 3 góc nhìn đối kháng, trình bày rõ ràng từng góc nhìn:

---

### 👨‍⚖️ GÓC NHÌN LUẬT SƯ BÀO CHỮA (Defense Attorney)

**Nhiệm vụ**: Bảo vệ quyền lợi tối đa cho bị can/bị cáo

Phân tích theo hướng CÓ LỢI:
1. **Tình tiết giảm nhẹ** (Điều 51 BLHS 2015): Tự thú, khai báo thành khẩn, khắc phục hậu quả, phạm tội lần đầu, hoàn cảnh khó khăn...
2. **Sơ hở tố tụng**: Có vi phạm thủ tục điều tra không? Chứng cứ có được thu thập hợp pháp không? Quyền bào chữa có bị xâm phạm không?
3. **Phản bác chứng cứ buộc tội**: Chứng cứ có đủ tin cậy không? Có mâu thuẫn lời khai không? Có bằng chứng ngoại phạm không?
4. **Phương án bào chữa**: Đề xuất miễn TNHS, giảm nhẹ hình phạt, hoặc chuyển đổi tội danh nhẹ hơn.

---

### ⚖️ GÓC NHÌN KIỂM SÁT VIÊN (Prosecutor)

**Nhiệm vụ**: Bảo vệ pháp chế, không bỏ sót tội phạm

Phân tích theo hướng BẤT LỢI:
1. **Cấu thành tội phạm**: Phân tích đầy đủ 4 yếu tố (Chủ thể, Khách thể, Mặt khách quan, Mặt chủ quan)
2. **Tình tiết tăng nặng** (Điều 52 BLHS 2015): Phạm tội có tổ chức, phạm tội nhiều lần, lợi dụng chức vụ...
3. **Chứng cứ buộc tội**: Vật chứng, lời khai, giám định, biên bản hiện trường...
4. **Đề nghị mức hình phạt**: Trong khung hình phạt nào? Án tù giam hay án treo?

---

### 🏛️ GÓC NHÌN THẨM PHÁN (Judge)

**Nhiệm vụ**: Phán quyết công bằng, thấu tình đạt lý

1. **Đánh giá cân bằng**: Xem xét bình đẳng lập luận của VKS và Luật sư
2. **Áp dụng Án lệ**: Có Án lệ nào có tình tiết tương tự không? Nguyên tắc pháp lý đã xác lập?
3. **Cá thể hóa hình phạt** (Điều 50 BLHS): Cân nhắc nhân thân, hoàn cảnh, mức độ nguy hiểm
4. **Kết luận**: Quyết định tội danh, mức hình phạt, và lý do phán quyết

---

⚠️ **LƯU Ý**: Mỗi góc nhìn phải TRÍCH DẪN CĂN CỨ PHÁP LÝ CỤ THỂ (Điều, Khoản, VBQPPL). Không được mơ hồ.
"""


def _build_civil_adversarial(query: str) -> str:
    """Instruction đối kháng cho tranh chấp dân sự/thương mại."""
    return """
## ⚔️ PHÂN TÍCH ĐA CHIỀU ĐỐI KHÁNG — TRANH CHẤP DÂN SỰ

Bạn PHẢI phân tích vấn đề pháp lý này đồng thời từ 3 góc nhìn đối kháng:

---

### 👨‍⚖️ GÓC NHÌN BẢO VỆ BÊN YẾU THẾ (Luật sư bảo vệ quyền lợi)

1. **Quyền lợi hợp pháp bị xâm phạm**: Xác định cụ thể quyền gì bị vi phạm theo BLDS/Luật chuyên ngành
2. **Căn cứ yêu cầu bồi thường**: Thiệt hại thực tế, thiệt hại tinh thần, mất cơ hội kinh doanh...
3. **Chứng cứ có lợi**: Hợp đồng, biên bản, tin nhắn, nhân chứng...
4. **Thời hiệu khởi kiện**: Còn trong thời hiệu không?
5. **Phương án pháp lý tối ưu**: Hòa giải, thương lượng, hay khởi kiện tại Tòa?

---

### ⚖️ GÓC NHÌN BẢO VỆ BÊN CÒN LẠI (Luật sư đối phương)

1. **Phản bác yêu cầu**: Lý do hợp pháp để bác bỏ yêu cầu của bên kia
2. **Căn cứ miễn trách**: Bất khả kháng, lỗi của chính bên kia, quyết định của cơ quan có thẩm quyền...
3. **Chứng cứ phản bác**: Bằng chứng hợp đồng đã thực hiện, biên bản thanh lý...
4. **Yêu cầu phản tố**: Có thể đưa ra yêu cầu phản tố không?

---

### 🏛️ GÓC NHÌN THẨM PHÁN (Phán quyết công bằng)

1. **Đánh giá chứng cứ hai bên**: Bên nào có chứng cứ thuyết phục hơn?
2. **Áp dụng nguyên tắc**: Thiện chí, trung thực, bảo vệ người thứ ba ngay tình
3. **Án lệ tương tự**: Các vụ việc tương tự Tòa đã xử thế nào?
4. **Phán quyết đề xuất**: Chấp nhận/bác bỏ yêu cầu, mức bồi thường

---

⚠️ **LƯU Ý**: Mỗi góc nhìn phải TRÍCH DẪN CĂN CỨ PHÁP LÝ CỤ THỂ (Điều, Khoản, VBQPPL). Không được mơ hồ.
"""


if __name__ == "__main__":
    test_queries = [
        "Anh A bị công an bắt vì tội trộm cắp, có phạm tội không?",
        "Hợp đồng mua bán bất động sản bị vô hiệu, ai đúng ai sai?",
        "Thời tiết hôm nay thế nào?",  # Should return False
    ]
    
    for q in test_queries:
        should = should_use_adversarial(q)
        print(f"Query: {q[:60]}... | Adversarial: {should}")
        if should:
            instruction = build_adversarial_instruction(q)
            print(f"  Instruction length: {len(instruction)} chars")
