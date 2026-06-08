import os
import sys
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run():
    from app.routers.laws import get_smart_search_resources
    import faiss
    
    model, _ = get_smart_search_resources()
    if model is None:
        print("Không thể load model")
        return
        
    q_base = "Thời gian thử việc tối đa đối với người lao động trình độ đại học là bao lâu?"
    
    candidates = [
        ("Tương tự 1", "thử việc bằng đại học tối đa bao nhiêu ngày?"),
        ("Tương tự 2", "thời gian thử việc của trình độ đại học là mấy tháng?"),
        ("Tương tự 3", "thử việc trình độ đại học bao lâu?"),
        ("Khác 1 (Hình sự)", "Mức hình phạt tối đa đối với tội trộm cắp tài sản là gì?"),
        ("Khác 2 (Doanh nghiệp)", "Hồ sơ đăng ký thành lập công ty TNHH gồm những giấy tờ gì?"),
        ("Khác 3 (Đất đai)", "Thủ tục xin cấp sổ đỏ lần đầu cần những điều kiện gì?"),
    ]
    
    # Encode base query
    v_base = model.encode([q_base]).astype(np.float32)
    faiss.normalize_L2(v_base)
    
    print(f"Base Query: '{q_base}'\n")
    print("So sánh điểm tương đồng Cosine:")
    print("-" * 80)
    for label, text in candidates:
        v_cand = model.encode([text]).astype(np.float32)
        faiss.normalize_L2(v_cand)
        
        # Cosine similarity is dot product because vectors are normalized
        score = float(np.dot(v_base, v_cand.T)[0][0])
        print(f"[{label}] | Query: '{text}'")
        print(f"👉 Cosine Similarity Score: {score:.4f}\n")

if __name__ == "__main__":
    run()
