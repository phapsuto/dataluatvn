"""
Module Nhận diện Vai trò Người hỏi (User Role Detector) và Sinh Gợi ý Tương tác Kế tiếp (Interactive Follow-up Generator)
dành cho Trợ lý Pháp lý Lan Anh.
"""

import re
from typing import Dict, Any, List

def detect_user_role(query: str) -> Dict[str, str]:
    """
    Nhận diện danh xưng người hỏi dựa trên từ ngữ thực tế trong câu hỏi:
    - Nếu người dùng xưng/gọi là "Anh" -> Lan Anh xưng "em/Lan Anh", gọi "Anh".
    - Nếu người dùng xưng/gọi là "Chị" -> Lan Anh xưng "em/Lan Anh", gọi "Chị".
    - Nếu người dùng xưng/gọi "Bác/Cô/Chú/Ông/Bà" -> Lan Anh xưng "con/Lan Anh", gọi "Bác/Cô/Chú".
    - Nếu KHÔNG có danh xưng cụ thể -> Mặc định Lan Anh xưng "Lan Anh", gọi người dùng là "bạn" cho thân thương, gần gũi.
    """
    q_lower = query.lower().strip()
    
    # 1. Kiểm tra danh xưng Bác / Cô / Chú / Ông / Bà / Tuổi già
    elderly_patterns = [
        r"\b(con ơi|dạ con|bác|cô|chú|ông|bà|tuổi già|lương hưu|di chúc cho con cháu)\b",
        r"\b(tôi già rồi|tuổi xế chiều|cho con cái)\b"
    ]
    for pattern in elderly_patterns:
        if re.search(pattern, q_lower):
            return {
                "role": "nguoi_lon_tuoi",
                "self_name": "Lan Anh (hoặc con)",
                "user_name": "Bác/Cô/Chú",
                "tone": "Kính cẩn, lễ phép, mộc mạc, từ tốn"
            }

    # 2. Kiểm tra danh xưng Anh / Chị cụ thể
    if re.search(r"\b(cho anh|anh muốn|anh bị|anh đang|anh hỏi|anh làm)\b", q_lower):
        return {
            "role": "ca_nhan_anh",
            "self_name": "Lan Anh (hoặc em)",
            "user_name": "Anh",
            "tone": "Ấm áp, ân cần, thấu hiểu"
        }
    if re.search(r"\b(cho chị|chị muốn|chị bị|chị đang|chị hỏi|chị làm)\b", q_lower):
        return {
            "role": "ca_nhan_chi",
            "self_name": "Lan Anh (hoặc em)",
            "user_name": "Chị",
            "tone": "Ấm áp, ân cần, thấu hiểu"
        }

    # 3. Doanh nghiệp / HR / Sếp
    corp_patterns = [
        r"\b(công ty tôi|doanh nghiệp tôi|công ty của tôi|doanh nghiệp của tôi)\b",
        r"\b(trưởng phòng hr|nhân viên của tôi|người lao động của công ty|cho nghỉ việc nhân viên|kỷ luật nhân viên)\b",
        r"\b(hợp đồng thương mại|ngành nghề kinh doanh|thuế tndn|vốn điều lệ|cổ đông|hội đồng quản trị|điều lệ công ty|xuất hóa đơn)\b"
    ]
    for pattern in corp_patterns:
        if re.search(pattern, q_lower):
            return {
                "role": "doanh_nghiep",
                "self_name": "Lan Anh (hoặc em)",
                "user_name": "Quý Công ty / Anh/Chị",
                "tone": "Lịch sự, gãy gọn, chuyên nghiệp, tận tụy"
            }

    # 4. Sinh viên / Người nghiên cứu
    student_patterns = [
        r"\b(sinh viên|bài tập|đề tài|nghiên cứu|đồ án|giảng viên|môn học|tiểu luận|luận văn)\b",
        r"\b(cho hỏi thuyết|lý thuyết pháp luật)\b"
    ]
    for pattern in student_patterns:
        if re.search(pattern, q_lower):
            return {
                "role": "sinh_vien",
                "self_name": "Lan Anh",
                "user_name": "bạn",
                "tone": "Cởi mở, thân thiện, cởi mở trao đổi tri thức"
            }

    # 5. Mặc định (Khi người dùng không xưng hô danh xưng nào): Gọi là "bạn", xưng "Lan Anh" cho gần gũi và thân thương!
    return {
        "role": "ca_nhan_ban",
        "self_name": "Lan Anh",
        "user_name": "bạn",
        "tone": "Gần gũi, thân thương, ấm áp và thấu hiểu"
    }


def generate_lan_anh_followups(query: str, domain: str = "general") -> str:
    """
    Sinh khối Markdown Gợi ý Tương tác kế tiếp tự nhiên, không dùng từ 'Góc nhìn',
    giúp định hướng câu trả lời tiếp theo cho người dùng.
    """
    q_lower = query.lower()
    
    # 1. Lĩnh vực Hình sự / Mua dâm / Lừa đảo / Chiếm đoạt
    if any(k in q_lower for k in ["lừa đảo", "chuyển khoản", "tội", "hình sự", "công an", "trộm cắp", "chiếm đoạt", "mại dâm", "mua dâm", "thủ kho"]) or domain == "hinh_su":
        return """
---

💬 **Anh/Chị có muốn Lan Anh hỗ trợ phân tích sâu hơn theo hướng nào tiếp theo không ạ?**

👉 Quy trình Cơ quan Công an xác minh, điều tra và thu hồi tài sản bị chiếm đoạt?
👉 Các giải pháp quản lý & rà soát quy chế để phòng ngừa rủi ro tương tự?
👉 Hướng dẫn từng bước soạn Đơn trình báo / Đơn tố giác gửi cơ quan có thẩm quyền?
"""

    # 2. Lĩnh vực Lao động & HR
    if any(k in q_lower for k in ["sa thải", "đuổi việc", "thử việc", "lương", "bhxh", "hợp đồng lao động", "bồi thường"]) or domain == "lao_dong":
        return """
---

💬 **Anh/Chị có muốn Lan Anh hỗ trợ phân tích sâu hơn theo hướng nào tiếp theo không ạ?**

👉 Mức xử phạt hành chính đối với doanh nghiệp nếu vi phạm quy định lao động?
👉 Phương án thương lượng và đàm phán bồi thường tối ưu nhất cho Anh/Chị?
👉 Hướng dẫn chi tiết quy trình và cách viết Đơn khiếu nại lao động chuẩn pháp lý?
"""

    # 3. Lĩnh vực Đất đai & Bất động sản
    if any(k in q_lower for k in ["đất", "sổ đỏ", "thu hồi", "tranh chấp đất", "sang tên", "nhà đất", "quy hoạch"]) or domain == "dat_dai":
        return """
---

💬 **Anh/Chị có muốn Lan Anh hỗ trợ phân tích sâu hơn theo hướng nào tiếp theo không ạ?**

👉 Tỷ lệ tranh chấp, cơ hội thắng kiện và chứng cứ pháp lý cần chuẩn bị?
👉 Những rủi ro cần tránh khi ký hợp đồng đặt cọc hoặc sang tên nhà đất?
👉 Quy trình và cách viết Đơn đề nghị hòa giải tranh chấp đất đai gửi UBND Xã/Phường?
"""

    # 4. Mặc định / Tổng hợp
    return """
---

💬 **Anh/Chị có muốn Lan Anh hỗ trợ phân tích sâu hơn theo hướng nào tiếp theo không ạ?**

👉 Đánh giá chi tiết khả năng bảo vệ quyền lợi và danh mục chứng cứ cần thu thập?
👉 Các rủi ro tiềm ẩn phát sinh và giải pháp chủ động phòng ngừa hiệu quả nhất?
👉 Hướng dẫn quy trình chuẩn bị hồ sơ và soạn thảo văn bản/đơn từ liên quan?
"""
