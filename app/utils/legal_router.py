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
            embeddings = embeddings.astype(np.float32)
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
    query_vector = query_vector.astype(np.float32)
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
            
    # Bắt buộc chuyển thành câu hỏi pháp luật nếu chứa các ký hiệu đặc trưng pháp lý
    # Ví dụ: "Điều 24", hoặc số hiệu văn bản "111/2009/NĐ-CP", "27-LCT/HĐNN8"
    # Chuẩn hóa khoảng trắng quanh dấu gạch chéo để bắt các số hiệu có khoảng trắng thừa (ví dụ: '6  /2007/QĐ-UBND')
    query_normalized_spaces = re.sub(r'\s*/\s*', '/', query)
    
    has_legal_identifier = False
    
    # 1. Check regex for Điều or số hiệu văn bản
    if (re.search(r'[Đđ]iều\s+\d+', query_normalized_spaces) or 
        re.search(r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|\b\d+-[A-Za-zĐđÀ-ỹ]{2,}\b)', query_normalized_spaces)):
        has_legal_identifier = True
        
    # 2. Check general legal keywords to prevent false positives in chitchat/out_of_scope
    legal_keywords = [
        "điều luật", "điều khoản", "nghị quyết", "thông tư", "nghị định", "quyết định", 
        "bộ luật", "luật pháp", "pháp luật việt nam", "văn bản pháp luật"
    ]
    query_lower = query.lower()
    if not has_legal_identifier and any(k in query_lower for k in legal_keywords):
        has_legal_identifier = True
        
    is_legal = best_domain not in ["chitchat", "out_of_scope"]
    
    if has_legal_identifier:
        is_legal = True
        if best_domain in ["chitchat", "out_of_scope"]:
            best_domain = "dan_su"  # Default fallback legal domain
    
    # We apply a conservative confidence threshold. If a query matches out_of_scope but has very low score,
    # we default to "dan_su" to prevent false negatives.
    if best_domain == "out_of_scope" and best_score < 0.25:
        best_domain = "dan_su"
        is_legal = True

    # Xác định Cấp độ Định tuyến
    # FIX TRIỆT ĐỂ: Không còn Level 2.
    # Tất cả câu hỏi pháp luật → Level 1 (Full RAG: FTS5 + FAISS Vector + Graph + Vietnamese Reranker)
    # Level 2 đã bị chứng minh sai 21% trong test 100 câu vì bỏ qua Vector/Graph/Reranker.
    if not is_legal or best_domain in ["chitchat", "out_of_scope"]:
        routing_level = 0  # Non-legal: handled separately in chatbot.py
    else:
        routing_level = 1  # ALL legal queries → Full RAG pipeline

    # Bóc tách metadata từ câu hỏi (Year, Doc Type, Issuer)
    # Bóc tách năm ban hành (Year) cực kỳ cẩn thận
    year_filter = None
    query_lower = query.lower()
    
    # 1. Trích xuất từ số hiệu văn bản có gạch chéo/gạch nối (ví dụ: /2024/, -2024-, /2024-NĐ)
    year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})[-/]', query)
    if not year_in_symbol_match:
        # Ví dụ: 12/2024/NĐ-CP hoặc 12/2024-NĐ-CP
        year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})[-/][A-ZĐđ]', query)
    if not year_in_symbol_match:
        # Ví dụ: 12/2024-NĐ
        year_in_symbol_match = re.search(r'[-/]((?:19|20)\d{2})-[A-ZĐđ]', query)
    if not year_in_symbol_match:
        # Ví dụ ở cuối số ký hiệu: 15/2024
        year_in_symbol_match = re.search(r'\b\d+/((?:19|20)\d{2})\b', query)
        
    if year_in_symbol_match:
        year_filter = int(year_in_symbol_match.group(1))
    else:
        # 2. Hoặc xuất hiện dạng "năm 2024" nhưng KHÔNG có "nhiệm kỳ" hay "giai đoạn" đi kèm
        if not re.search(r'(nhiệm kỳ|giai đoạn|kế hoạch)\s+\d+', query_lower):
            year_word_match = re.search(r'\bnăm\s+((?:19|20)\d{2})\b', query_lower)
            if year_word_match:
                year_filter = int(year_word_match.group(1))

    doc_type = None
    query_lower = query.lower()
    if "hiến pháp" in query_lower:
        doc_type = "Hiến pháp"
    elif "bộ luật" in query_lower:
        doc_type = "Bộ luật"
    elif "luật" in query_lower:
        # Avoid false positives where "luật" is part of non-document compounds
        exclude_words = ["pháp luật", "điều luật", "luật sư", "luật pháp", "kỷ luật", "tiền lệ luật"]
        if not any(ew in query_lower for ew in exclude_words):
            doc_type = "Luật"
    elif "nghị định" in query_lower:
        doc_type = "Nghị định"
    elif "thông tư liên tịch" in query_lower:
        doc_type = "Thông tư liên tịch"
    elif "thông tư" in query_lower:
        doc_type = "Thông tư"
    elif "quyết định" in query_lower:
        doc_type = "Quyết định"
    elif "nghị quyết" in query_lower:
        doc_type = "Nghị quyết"
    elif "pháp lệnh" in query_lower:
        doc_type = "Pháp lệnh"
    elif "chỉ thị" in query_lower:
        doc_type = "Chỉ thị"

    issuer = None
    if "chính phủ" in query_lower:
        issuer = "Chính phủ"
    elif "thủ tướng" in query_lower:
        issuer = "Thủ tướng Chính phủ"
    elif "bộ tài chính" in query_lower:
        issuer = "Bộ Tài chính"
    elif "bộ y tế" in query_lower:
        issuer = "Bộ Y tế"
    elif "bộ công thương" in query_lower:
        issuer = "Bộ Công thương"
    elif "bộ giáo dục" in query_lower or "bộ gd&đt" in query_lower or "bộ gd-đt" in query_lower:
        issuer = "Bộ Giáo dục và Đào tạo"
    elif "bộ lao động" in query_lower or "bộ ldtbxh" in query_lower or "bộ lđtbxh" in query_lower or "thương binh và xã hội" in query_lower:
        issuer = "Bộ Lao động - Thương binh và Xã hội"
    elif "bộ công an" in query_lower:
        issuer = "Bộ Công an"
    elif "bộ quốc phòng" in query_lower:
        issuer = "Bộ Quốc phòng"
    elif "bộ tư pháp" in query_lower:
        issuer = "Bộ Tư pháp"
    elif "bộ xây dựng" in query_lower:
        issuer = "Bộ Xây dựng"
    elif "bộ giao thông" in query_lower or "bộ gtvt" in query_lower:
        issuer = "Bộ Giao thông vận tải"
    elif "bộ kế hoạch" in query_lower or "bộ kh&đt" in query_lower or "bộ kh-đt" in query_lower:
        issuer = "Bộ Kế hoạch và Đầu tư"
    elif "bộ tài nguyên" in query_lower or "bộ tn&mt" in query_lower or "bộ tn-mt" in query_lower:
        issuer = "Bộ Tài nguyên và Môi trường"
    elif "bộ thông tin" in query_lower or "bộ tt&tt" in query_lower or "bộ tt-tt" in query_lower:
        issuer = "Bộ Thông tin và Truyền thông"
    elif "bộ nông nghiệp" in query_lower or "bộ nn&ptnt" in query_lower or "bộ nn-ptnt" in query_lower:
        issuer = "Bộ Nông nghiệp và Phát triển nông thôn"
    elif "quốc hội" in query_lower:
        issuer = "Quốc hội"
    elif "ủy ban thường vụ quốc hội" in query_lower or "ubtvqh" in query_lower:
        issuer = "Ủy ban Thường vụ Quốc hội"
    elif "tòa án nhân dân tối cao" in query_lower or "tandtc" in query_lower:
        issuer = "Tòa án nhân dân tối cao"
    elif "viện kiểm sát" in query_lower or "vksndtc" in query_lower:
        issuer = "Viện kiểm sát nhân dân tối cao"
        
    return {
        "domain": best_domain,
        "confidence": best_score,
        "doc_type_filter": DOMAIN_FILTERS.get(best_domain, []),
        "is_legal": is_legal,
        "routing_level": routing_level,
        "extracted_year": year_filter,
        "extracted_doc_type": doc_type,
        "extracted_issuer": issuer
    }
