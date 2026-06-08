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
        ("Khác thực thể (cao đẳng)", "Thời gian thử việc tối đa đối với người lao động trình độ cao đẳng là bao lâu?"),
        ("Khác thực thể (trung cấp)", "Thời gian thử việc tối đa đối với người lao động trình độ trung cấp là bao lâu?"),
        ("Khác thực thể (sơ cấp)", "Thời gian thử việc tối đa đối với người lao động trình độ sơ cấp là bao lâu?"),
        ("Viết lại cùng nghĩa", "thời gian thử việc của trình độ đại học là mấy tháng?"),
    ]
    
    v_base = model.encode([q_base]).astype(np.float32)
    faiss.normalize_L2(v_base)
    
    print(f"Base Query: '{q_base}'\n")
    print("So sánh điểm tương đồng Cosine để xem độ nhạy thực thể:")
    print("-" * 80)
    for label, text in candidates:
        v_cand = model.encode([text]).astype(np.float32)
        faiss.normalize_L2(v_cand)
        
        score = float(np.dot(v_base, v_cand.T)[0][0])
        print(f"[{label}] | Query: '{text}'")
        print(f"👉 Cosine Similarity Score: {score:.4f}\n")

if __name__ == "__main__":
    run()
