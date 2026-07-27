"""
blind_spot_engine.py — Blind-Spot Fact Engine (BSFE) & Conditional Branching
DataLuatVN RAG Gen 4 (Enterprise Legal Cognitive Engine)

Detects missing critical facts (BSF-01 to BSF-11) from user queries and generates
adaptive conditional branching recommendations for CITIZEN, ENTERPRISE, and JUDICIAL tiers.
"""

from typing import Dict, List, Any


class BSFSeverity:
    CRITICAL = "CRITICAL"  # Thiếu dữ kiện có thể làm đảo chiều hoàn toàn kết luận đúng/sai
    MAJOR = "MAJOR"        # Thiếu dữ kiện ảnh hưởng đến mức độ bồi thường / vi phạm thủ tục
    MINOR = "MINOR"        # Thiếu dữ kiện chi tiết phụ


BSF_CATALOG = {
    "BSF-01": {
        "id": "BSF-01",
        "name": "Quy chế đánh giá mức độ hoàn thành công việc",
        "question": "Công ty đã ban hành Quy chế đánh giá KPI có tham khảo ý kiến tổ chức công đoàn chưa?",
        "severity": BSFSeverity.CRITICAL,
        "keywords": ["không hoàn thành", "kpi", "đuổi việc", "sa thải", "đánh giá"]
    },
    "BSF-02": {
        "id": "BSF-02",
        "name": "Loại Hợp đồng Lao động & Thời hạn báo trước",
        "question": "Hợp đồng lao động của anh/chị là loại xác định thời hạn (<12 tháng hay >=12 tháng) hay không xác định thời hạn?",
        "severity": BSFSeverity.CRITICAL,
        "keywords": ["hợp đồng", "báo trước", "ngày", "đơn phương", "chấm dứt"]
    },
    "BSF-03": {
        "id": "BSF-03",
        "name": "Hình thức thông báo chấm dứt HĐLĐ",
        "question": "Công ty gửi thông báo bằng văn bản chính thức hay chỉ nói miệng/nhắn tin?",
        "severity": BSFSeverity.MAJOR,
        "keywords": ["thông báo", "báo trước", "nghỉ", "đơn phương"]
    },
    "BSF-04": {
        "id": "BSF-04",
        "name": "Tình trạng đặc thù bảo vệ (Thai sản / Nuôi con dưới 12 tháng)",
        "question": "Người lao động có đang mang thai, nghỉ thai sản, hoặc nuôi con dưới 12 tháng tuổi không?",
        "severity": BSFSeverity.CRITICAL,
        "keywords": ["nữ", "thai", "con", "sa thải", "đơn phương", "mang thai"]
    },
    "BSF-05": {
        "id": "BSF-05",
        "name": "Thẩm quyền người ký quyết định / thông báo",
        "question": "Người ký thông báo chấm dứt hợp đồng có đúng thẩm quyền theo điều lệ hoặc ủy quyền không?",
        "severity": BSFSeverity.MAJOR,
        "keywords": ["giám đốc", "ký", "thẩm quyền", "thông báo", "quyết định"]
    }
}


class BlindSpotFactEngine:
    """
    Blind-Spot Fact Engine (BSFE) for DataLuatVN RAG Gen 4.
    Identifies missing critical facts and produces adaptive formatting per Tri-Tier mode.
    """

    @staticmethod
    def detect_blind_spots(query: str, max_items: int = 3) -> List[Dict[str, Any]]:
        """
        Scan user query text against BSF catalog to find relevant blind spots
        that aren't explicitly clarified in the query.
        """
        q_lower = query.lower()
        detected = []
        for bsf_id, bsf in BSF_CATALOG.items():
            # If query touches relevant keywords
            if any(kw in q_lower for kw in bsf["keywords"]):
                # Simple check: see if query already has explicit answers
                detected.append(bsf)
                if len(detected) >= max_items:
                    break
        return detected

    @staticmethod
    def generate_conditional_branching_text(
        blind_spots: List[Dict[str, Any]],
        access_tier: str = "CITIZEN"
    ) -> str:
        """
        Generate adaptive Markdown output for detected Blind-Spot Facts
        tailored to CITIZEN, ENTERPRISE, or JUDICIAL tiers.
        """
        if not blind_spots:
            return ""

        tier = (access_tier or "CITIZEN").upper()

        if tier == "CITIZEN":
            lines = [
                "\n### 📋 3 BƯỚC ANH/CHỊ CẦN CHUẨN BỊ NGAY ĐỂ BẢO VỆ QUYỀN LỢI:",
                "Để kết luận pháp lý chính xác 100%, anh/chị cần kiểm tra nhanh các giấy tờ sau:"
            ]
            for idx, item in enumerate(blind_spots, 1):
                lines.append(f"{idx}. **{item['name']}:** {item['question']}")
            lines.append("👉 *Nếu công ty không có đủ căn cứ trên, việc cho anh/chị nghỉ là **trái luật**.*")
            return "\n".join(lines)

        elif tier == "ENTERPRISE":
            lines = [
                "\n### 🏢 MA TRẬN RỦI RO TUÂN THỦ (STATUTORY CONFLICT SCANNER):",
                "**Các điểm khuyết dữ kiện quản trị (Compliance Blind-Spots) cần rà soát:**"
            ]
            for item in blind_spots:
                sev_badge = f"**[{item['severity']}]**"
                lines.append(f"- {sev_badge} **{item['name']}** -> *{item['question']}*")
            lines.append("⚠️ *Khuyến nghị: Bổ sung ngay hồ sơ pháp lý nội bộ để loại trừ rủi ro bồi thường vi phạm Điều 41 BLLĐ.*")
            return "\n".join(lines)

        else:  # JUDICIAL
            lines = [
                "\n### ⚖️ MA TRẬN PHÂN NHÁNH ĐIỀU KIỆN TÀI PHÁN (BSFE CONDITIONAL TREE):",
                "**Các Dữ kiện Quyết định Khuyết thiếu (Normative Blind-Spots) & Lập luận phân nhánh:**"
            ]
            for item in blind_spots:
                lines.append(f"- `[{item['id']} - {item['severity']}]`: **{item['name']}**")
                lines.append(f"  - *Vấn đề tài phán:* {item['question']}")
                if item["severity"] == BSFSeverity.CRITICAL:
                    lines.append("  - *Hệ quả phân nhánh:* Nếu thiếu hoặc không đủ căn cứ -> Tuyên vô hiệu / Vi phạm pháp luật lao động nghiêm trọng.")
            return "\n".join(lines)
