import datetime
from typing import Dict, Any, Optional

def get_document_rank(loai_van_ban: Optional[str], co_quan_ban_hanh: Optional[str], so_ky_hieu: Optional[str]) -> int:
    """
    Xác định cấp bậc hiệu lực pháp lý (Rank) của văn bản.
    Rank từ 15 đến 100. Càng cao hiệu lực càng mạnh.
    
    Cơ chế phân cấp tuân thủ Điều 4 Luật ban hành văn bản quy phạm pháp luật 2015
    và tích hợp đúng 3 cấp chính quyền địa phương (Tỉnh -> Huyện -> Xã).
    """
    loai = (loai_van_ban or "").strip().lower()
    co_quan = (co_quan_ban_hanh or "").strip().lower()
    ky_hieu = (so_ky_hieu or "").strip().upper()

    # Kiểm tra xem có phải văn bản của chính quyền địa phương không
    # (Hội đồng nhân dân HĐND, Ủy ban nhân dân UBND)
    is_local = False
    if any(x in ky_hieu for x in ["HĐND", "UBND"]) or any(x in co_quan for x in ["hội đồng nhân dân", "ủy ban nhân dân"]):
        is_local = True

    if is_local:
        # Hệ thống chỉ còn cấp Tỉnh và cấp Xã (Phường) theo yêu cầu mới
        # Cấp Xã (Xã, Phường, Thị trấn)
        if any(w in co_quan for w in ["xã", "phường", "thị trấn"]):
            return 20
        # Cấp Tỉnh (Tỉnh, Thành phố trực thuộc trung ương)
        return 40

    # Cấp Trung ương
    if loai == "hiến pháp":
        return 100
    elif loai in ["bộ luật", "luật"]:
        return 90
    elif loai == "pháp lệnh":
        return 80
    elif loai == "nghị quyết":
        if "quốc hội" in co_quan:
            return 85
        elif "chính phủ" in co_quan:
            return 70
        elif "thẩm phán" in co_quan or "tòa án nhân dân tối cao" in co_quan or "tandtc" in co_quan:
            return 60
        return 85
    elif loai == "lệnh":
        return 75
    elif loai == "nghị định":
        return 70
    elif loai == "quyết định":
        if "thủ tướng" in co_quan:
            return 65
        if "chủ tịch nước" in co_quan:
            return 75
        return 65
    elif loai in ["thông tư", "thông tư liên tịch", "nghị quyết liên tịch", "thông tư liên bộ"]:
        return 50
    elif loai == "chỉ thị":
        return 45
    
    return 15  # Các loại văn bản khác hành chính bình thường


def compare_hierarchy(doc_a: Dict[str, Any], doc_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    So sánh hiệu lực pháp lý giữa hai văn bản dựa trên Điều 156 Luật 80/2015/QH13.
    Trả về cấu trúc quyết định ưu tiên.
    """
    rank_a = get_document_rank(doc_a.get("loai_van_ban"), doc_a.get("co_quan_ban_hanh"), doc_a.get("so_ky_hieu"))
    rank_b = get_document_rank(doc_b.get("loai_van_ban"), doc_b.get("co_quan_ban_hanh"), doc_b.get("so_ky_hieu"))

    if rank_a > rank_b:
        return {
            "preferred": doc_a,
            "non_preferred": doc_b,
            "reason": f"Hiệu lực pháp lý cao hơn ({doc_a.get('loai_van_ban')} có Rank {rank_a} > {doc_b.get('loai_van_ban')} có Rank {rank_b})",
            "clause": "Điều 156 khoản 1 Luật ban hành văn bản QPPL 2015 (Áp dụng văn bản có hiệu lực pháp lý cao hơn)."
        }
    elif rank_b > rank_a:
        return {
            "preferred": doc_b,
            "non_preferred": doc_a,
            "reason": f"Hiệu lực pháp lý cao hơn ({doc_b.get('loai_van_ban')} có Rank {rank_b} > {doc_a.get('loai_van_ban')} có Rank {rank_a})",
            "clause": "Điều 156 khoản 1 Luật ban hành văn bản QPPL 2015 (Áp dụng văn bản có hiệu lực pháp lý cao hơn)."
        }

    # Nếu cùng Rank, kiểm tra xem có cùng cơ quan ban hành không
    agency_a = (doc_a.get("co_quan_ban_hanh") or "").strip().lower()
    agency_b = (doc_b.get("co_quan_ban_hanh") or "").strip().lower()
    
    # Rút gọn chuỗi cơ quan ban hành để so khớp tương đối (ví dụ: cùng là HĐND tỉnh)
    is_same_agency = (agency_a == agency_b) or (len(agency_a) > 5 and len(agency_b) > 5 and (agency_a in agency_b or agency_b in agency_a))

    if is_same_agency:
        # Cùng cơ quan ban hành và cùng cấp hiệu lực -> Áp dụng văn bản ban hành sau (Khoản 2 Điều 156)
        date_a_str = doc_a.get("ngay_ban_hanh") or "1970-01-01"
        date_b_str = doc_b.get("ngay_ban_hanh") or "1970-01-01"
        
        if date_a_str > date_b_str:
            return {
                "preferred": doc_a,
                "non_preferred": doc_b,
                "reason": f"Cùng cấp bậc hiệu lực và cơ quan ban hành, văn bản {doc_a.get('so_ky_hieu')} ban hành sau ({date_a_str} > {date_b_str})",
                "clause": "Điều 156 khoản 2 Luật ban hành văn bản QPPL 2015 (Do cùng cơ quan ban hành, áp dụng văn bản ban hành sau)."
            }
        elif date_b_str > date_a_str:
            return {
                "preferred": doc_b,
                "non_preferred": doc_a,
                "reason": f"Cùng cấp bậc hiệu lực và cơ quan ban hành, văn bản {doc_b.get('so_ky_hieu')} ban hành sau ({date_b_str} > {date_a_str})",
                "clause": "Điều 156 khoản 2 Luật ban hành văn bản QPPL 2015 (Do cùng cơ quan ban hành, áp dụng văn bản ban hành sau)."
            }

    # Không cùng cơ quan ban hành, nhưng cùng Rank (ví dụ: Thông tư của hai Bộ trưởng khác nhau quy định chéo nhau)
    # Theo nguyên tắc chung của Luật ban hành VBQPPL, các văn bản của Bộ trưởng ngang hàng không được trái nhau.
    # Nếu có mâu thuẫn, thường áp dụng văn bản ban hành sau hoặc theo hướng dẫn của cấp trên.
    # Trong hệ thống, ta trả về cảnh báo xung đột thẩm quyền.
    date_a_str = doc_a.get("ngay_ban_hanh") or "1970-01-01"
    date_b_str = doc_b.get("ngay_ban_hanh") or "1970-01-01"
    preferred_doc = doc_a if date_a_str >= date_b_str else doc_b
    non_preferred_doc = doc_b if date_a_str >= date_b_str else doc_a
    
    return {
        "preferred": preferred_doc,
        "non_preferred": non_preferred_doc,
        "reason": f"Cùng cấp bậc hiệu lực ({rank_a}) nhưng khác cơ quan ban hành ({doc_a.get('co_quan_ban_hanh')} vs {doc_b.get('co_quan_ban_hanh')}). Mặc định đề xuất văn bản mới hơn.",
        "clause": "Xung đột quy định chéo giữa các cơ quan ngang hàng (Cần rà soát thẩm quyền chi tiết)."
    }
