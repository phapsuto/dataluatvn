import numpy as np
import re
from typing import Dict, Any, List

# Define domain mapping, representative utterances, and SQL filter keywords
UTTERANCES = {
    "lao_dong": [
        "hợp đồng lao động", "sa thải nhân viên trái luật", "đơn phương chấm dứt hợp đồng lao động", 
        "mức lương tối thiểu vùng", "bảo hiểm xã hội bắt buộc", "chế độ thai sản hiểm nghèo", "tai nạn lao động", 
        "thời gian thử việc", "trợ cấp thôi việc mất việc", "lương tháng 13", "công đoàn cơ sở", "thời giờ làm việc nghỉ ngơi"
    ],
    "dan_su": [
        "chia thừa kế theo pháp luật", "di chúc hợp pháp có công chứng", "tranh chấp tài sản chung vợ chồng", "thủ tục ly hôn đơn phương", 
        "quyền nuôi con sau ly hôn", "hợp đồng dân sự vô hiệu", "bồi thường thiệt hại ngoài hợp đồng", "tặng cho tài sản thế chấp", 
        "đặt cọc mua bán nhà đất", "hợp đồng ủy quyền", "thực hiện nghĩa vụ dân sự", "kết hôn với người nước ngoài"
    ],
    "hinh_su": [
        "phạm tội giết người cướp của", "quyết định khởi tố vụ án hình sự", "tố tụng hình sự sơ thẩm phúc thẩm", "bắt tạm giam bị can bị cáo", 
        "khung hình phạt cao nhất", "tội trộm cắp tài sản công dân", "cố ý gây thương tích tổn hại sức khỏe", "án treo thử thách", 
        "tội lừa đảo chiếm đoạt tài sản", "người bào chữa luật sư", "đồng phạm trong vụ án", "tình tiết giảm nhẹ trách nhiệm hình sự"
    ],
    "dat_dai": [
        "tranh chấp đất đai đền bù giải phóng mặt bằng", "thủ tục cấp sổ đỏ quyền sử dụng đất", "chuyển nhượng quyền sử dụng đất đai", 
        "thu hồi đất giải phóng mặt bằng tái định cư", "đất nông nghiệp đất trồng lúa", "giá đền bù đất đai giải tỏa", 
        "tách thửa đất đai", "tranh chấp lối đi chung nhà hàng xóm", "quy hoạch đất đai đô thị", "thuế nhà đất lệ phí trước bạ"
    ],
    "doanh_nghiep": [
        "thành lập công ty cổ phần trách nhiệm hữu hạn", "thay đổi đăng ký kinh doanh giấy phép", "vốn điều lệ doanh nghiệp", 
        "quyền của cổ đông thành viên", "giải thể doanh nghiệp công ty", "thủ tục phá sản doanh nghiệp", "hợp đồng thương mại quốc tế", 
        "góp vốn thành lập doanh nghiệp", "chuyển nhượng cổ phần phần vốn góp", "đại hội đồng cổ đông hội đồng quản trị"
    ],
    "hanh_chinh": [
        "xử phạt vi phạm hành chính", "thủ tục xin cấp giấy phép con", "khiếu nại quyết định hành chính hành vi hành chính", 
        "tố cáo hành vi vi phạm pháp luật", "cưỡng chế hành chính thu hồi", "thuế thu nhập cá nhân doanh nghiệp", "hộ chiếu căn cước công dân", 
        "đăng ký tạm trú tạm vắng thường trú", "giấy phép xây dựng nhà ở", "vi phạm luật giao thông đường bộ"
    ],
    "chitchat": [
        "chào bạn", "hello", "hi", "cảm ơn bạn nhé", "tạm biệt", "bạn là ai", 
        "chúc một ngày tốt lành", "tư vấn giúp tôi với", "bạn tên là gì", "help me"
    ],
    "out_of_scope": [
        "chữa bệnh đau dạ dày thế nào", "công thức nấu món ăn ngon", "cách sửa máy tính hỏng", 
        "luật pháp nước mỹ hoa kỳ", "học tiếng anh ở đâu tốt", "giá cổ phiếu chứng khoán hôm nay", 
        "thời tiết ngày mai thế nào", "xu hướng thời trang mới", "kết quả bóng đá ngoại hạng anh"
    ]
}

# Domain Filters (keywords to match in document titles or types)
DOMAIN_FILTERS = {
    "lao_dong": ["Lao động", "BHXH", "Bảo hiểm xã hội", "Công đoàn", "Việc làm", "Hưu trí"],
    "dan_su": ["Dân sự", "Hôn nhân", "Gia đình", "Di chúc", "Thừa kế", "Hợp đồng"],
    "hinh_su": ["Hình sự", "Tố tụng hình sự", "Tội phạm", "Hình phạt", "Bị can", "Bị cáo"],
    "dat_dai": ["Đất đai", "Nhà ở", "Bất động sản", "Nhà đất", "Sổ đỏ"],
    "doanh_nghiep": ["Doanh nghiệp", "Đầu tư", "Phá sản", "Thương mại", "Cổ phần", "Doanh nhân"],
    "hanh_chinh": ["Vi phạm hành chính", "Khiếu nại", "Tố cáo", "Xử phạt hành chính", "Hộ tịch", "Hành chính"],
    "chitchat": [],
    "out_of_scope": []
}

# In-memory cache for computed utterance embeddings
_UTTERANCE_EMBEDDINGS = {}

def get_utterance_embeddings(model) -> Dict[str, np.ndarray]:
    """Helper to lazily compute and cache L2-normalized embeddings of reference utterances."""
    global _UTTERANCE_EMBEDDINGS
    import faiss
    if not _UTTERANCE_EMBEDDINGS:
        for domain, texts in UTTERANCES.items():
            embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            faiss.normalize_L2(embeddings)
            _UTTERANCE_EMBEDDINGS[domain] = embeddings
    return _UTTERANCE_EMBEDDINGS

def route_query(query: str) -> Dict[str, Any]:
    """
    Routes a user's natural language query using Cosine Similarity on our local GPU-backed Bi-Encoder.
    Returns:
        {
            "domain": str (e.g. "lao_dong", "chitchat"),
            "confidence": float,
            "doc_type_filter": List[str],
            "is_legal": bool
        }
    """
    from app.routers.laws import get_smart_search_resources, normalize_spelling
    import faiss
    
    # Simple regex pre-check for chitchat/memory queries to save computation time and guarantee accuracy
    query_clean = re.sub(r'[^\w\s]', '', query.strip().lower())
    words = query_clean.split()
    
    short_chitchat = {"chào", "hello", "hi", "thanks", "cảm ơn", "cám ơn", "tạm biệt", "bye"}
    chitchat_phrases = [
        "bạn là ai", "bạn tên là gì", "ghi nhớ", "hãy ghi nhớ", "nhớ giúp", "nhớ giùm", "nhớ nhé", 
        "tên tôi là", "tên của tôi là", "tên công ty tôi", "tên công ty của tôi", 
        "công ty của tôi tên", "công ty tôi tên là", "tôi tên là gì", "tên tôi là gì", 
        "bạn có nhớ", "nhớ tôi không", "thông tin của tôi"
    ]
    
    is_chitchat = False
    for w in words:
        if w in short_chitchat:
            is_chitchat = True
            break
            
    if not is_chitchat:
        for phrase in chitchat_phrases:
            if phrase in query_clean:
                is_chitchat = True
                break
                
    if is_chitchat:
        return {
            "domain": "chitchat",
            "confidence": 1.0,
            "doc_type_filter": [],
            "is_legal": False
        }
        
    model, _ = get_smart_search_resources()
    if not model:
        # Fallback if model loading fails
        print("⚠️ Warning: Model resources not loaded in Router. Defaulting to 'dan_su'.")
        return {
            "domain": "dan_su",
            "confidence": 0.5,
            "doc_type_filter": DOMAIN_FILTERS["dan_su"],
            "is_legal": True
        }
        
    # Standardize spelling and encode query
    q_norm = normalize_spelling(query)
    query_vector = model.encode([q_norm], show_progress_bar=False, convert_to_numpy=True)
    faiss.normalize_L2(query_vector)
    
    # Fetch cached reference embeddings
    utterance_embs = get_utterance_embeddings(model)
    
    best_domain = "dan_su"
    best_score = -1.0
    
    for domain, embs in utterance_embs.items():
        # Compute Cosine Similarity via dot product of L2 normalized vectors
        scores = np.dot(embs, query_vector[0])
        max_score = float(np.max(scores))
        
        if max_score > best_score:
            best_score = max_score
            best_domain = domain
            
    is_legal = best_domain not in ["chitchat", "out_of_scope"]
    
    # We apply a conservative confidence threshold. If a query matches out_of_scope but has very low score,
    # we default to "dan_su" to prevent false negatives.
    if best_domain == "out_of_scope" and best_score < 0.25:
        best_domain = "dan_su"
        is_legal = True
        
    return {
        "domain": best_domain,
        "confidence": best_score,
        "doc_type_filter": DOMAIN_FILTERS.get(best_domain, []),
        "is_legal": is_legal
    }
