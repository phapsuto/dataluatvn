#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║    🧪 BENCHMARK: So sánh 3 LLM Models trên FPT Cloud               ║
║    Gemma-4-31B-it  vs  Qwen3-32B  vs  Saola-Llama3.1-Planner       ║
║    Đánh giá khả năng tư duy pháp lý Việt Nam                       ║
╚══════════════════════════════════════════════════════════════════════╝

Cách chạy:
    python3 scratch/benchmark_llm_models.py
"""

import os
import sys
import time
import json
import requests
from datetime import datetime

# ══════════════════════════════════════════════════
# CẤU HÌNH
# ══════════════════════════════════════════════════

FPT_API_KEY = os.environ.get(
    "FPT_CLOUD_API_KEY",
    "sk-o38ypse9lSfaKaDOQ9O7STlEbfZZ0PBLmJ1v_dwlSmM="
)
FPT_API_URL = "https://mkp-api.fptcloud.com/v1/chat/completions"

# 3 models cần benchmark
MODELS = {
    "gemma-4-31B-it": {
        "name": "Google Gemma 4 31B",
        "emoji": "🔷",
        "description": "Model đang dùng hiện tại trong LuatBot"
    },
    "Qwen3-32B": {
        "name": "Alibaba Qwen3 32B",
        "emoji": "🟢",
        "description": "Model mới, mạnh về tư duy logic & đa ngôn ngữ"
    },
    "SaoLa-Llama3.1-planner": {
        "name": "FPT Saola Planner (Llama3.1)",
        "emoji": "🟠",
        "description": "Model Việt Nam, tối ưu cho tiếng Việt"
    }
}

# ══════════════════════════════════════════════════
# BỘ CÂU HỎI BENCHMARK PHÁP LUẬT VIỆT NAM
# ══════════════════════════════════════════════════

LEGAL_QUESTIONS = [
    # ── Nhóm 1: Tra cứu điều khoản cụ thể ──
    {
        "id": "Q1",
        "category": "Tra cứu điều khoản",
        "question": "Điều 24 Luật Hôn nhân và Gia đình 2014 quy định về vấn đề gì?",
        "expected_keywords": ["hủy việc kết hôn trái pháp luật", "kết hôn trái", "hủy"],
        "difficulty": "Dễ"
    },
    {
        "id": "Q2",
        "category": "Tra cứu điều khoản",
        "question": "Theo Bộ luật Lao động 2019, thời giờ làm việc bình thường không quá bao nhiêu giờ trong 1 ngày?",
        "expected_keywords": ["8 giờ", "08 giờ", "không quá 8"],
        "difficulty": "Dễ"
    },

    # ── Nhóm 2: Phân tích tình huống pháp lý ──
    {
        "id": "Q3",
        "category": "Phân tích tình huống",
        "question": "Anh A ký hợp đồng lao động thời hạn 12 tháng. Sau 6 tháng, công ty đơn phương chấm dứt hợp đồng mà không báo trước. Anh A có quyền gì theo pháp luật?",
        "expected_keywords": ["bồi thường", "trợ cấp", "đơn phương chấm dứt", "trái pháp luật", "lương"],
        "difficulty": "Trung bình"
    },
    {
        "id": "Q4",
        "category": "Phân tích tình huống",
        "question": "Chị B và anh C ly hôn, có con chung 4 tuổi. Ai được quyền nuôi con theo quy định của Luật Hôn nhân và Gia đình?",
        "expected_keywords": ["dưới 36 tháng", "mẹ", "quyền nuôi", "3 tuổi", "thỏa thuận", "tòa án"],
        "difficulty": "Trung bình"
    },

    # ── Nhóm 3: So sánh và tổng hợp ──
    {
        "id": "Q5",
        "category": "So sánh tổng hợp",
        "question": "So sánh trách nhiệm hình sự giữa tội trộm cắp tài sản và tội cướp tài sản theo Bộ luật Hình sự 2015?",
        "expected_keywords": ["Điều 173", "Điều 168", "trộm cắp", "cướp", "hình phạt", "tù"],
        "difficulty": "Khó"
    },

    # ── Nhóm 4: Câu hỏi thực tiễn ──
    {
        "id": "Q6",
        "category": "Thực tiễn",
        "question": "Tôi muốn thành lập công ty TNHH 1 thành viên. Vốn điều lệ tối thiểu là bao nhiêu và cần những giấy tờ gì?",
        "expected_keywords": ["vốn điều lệ", "không quy định", "đăng ký kinh doanh", "giấy đề nghị", "CMND", "CCCD"],
        "difficulty": "Trung bình"
    },

    # ── Nhóm 5: Câu hỏi đánh lừa (trick question) ──
    {
        "id": "Q7",
        "category": "Câu hỏi đánh lừa",
        "question": "Theo pháp luật Việt Nam, trẻ em dưới 14 tuổi có được phép lái xe máy không?",
        "expected_keywords": ["không được", "cấm", "16 tuổi", "18 tuổi", "giấy phép lái xe", "vi phạm"],
        "difficulty": "Dễ"
    },

    # ── Nhóm 6: Câu hỏi cần suy luận nhiều bước ──
    {
        "id": "Q8",
        "category": "Suy luận đa bước",
        "question": "Ông D có 3 người con: E, F, G. Ông D chết không để lại di chúc. Tài sản thừa kế là 900 triệu đồng. Nhưng E đã chết trước ông D, E có 2 con là H và I. Hỏi H và I được thừa kế bao nhiêu tiền?",
        "expected_keywords": ["thừa kế thế vị", "150 triệu", "chia đều", "hàng thừa kế"],
        "difficulty": "Khó"
    },
]

# ══════════════════════════════════════════════════
# SYSTEM PROMPT PHÁP LÝ (giống với chatbot thực tế)
# ══════════════════════════════════════════════════

SYSTEM_PROMPT = """Bạn là LuatBot — Trợ lý pháp lý AI chuyên sâu về luật Việt Nam.

QUY TẮC BẮT BUỘC:
1. Trả lời chính xác dựa trên pháp luật Việt Nam hiện hành.
2. Trích dẫn số hiệu văn bản, điều khoản cụ thể khi có thể.
3. Nếu không biết hoặc không chắc chắn, hãy nói rõ "Tôi không có đủ thông tin" thay vì bịa đặt.
4. Trả lời bằng Tiếng Việt, ngắn gọn, chuyên nghiệp, dưới 300 từ.
5. Phân biệt rõ giữa các luật còn hiệu lực và đã hết hiệu lực."""


# ══════════════════════════════════════════════════
# HÀM GỌI API FPT CLOUD
# ══════════════════════════════════════════════════

def call_fpt_model(model_name: str, question: str, timeout: float = 60.0) -> dict:
    """Gọi API FPT Cloud cho 1 model cụ thể. Trả về response + metadata."""
    headers = {
        "Authorization": f"Bearer {FPT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        "temperature": 0.1,
        "max_tokens": 1024
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(
            FPT_API_URL,
            json=payload,
            headers=headers,
            timeout=timeout
        )
        latency = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            
            return {
                "status": "success",
                "content": content,
                "latency": latency,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        else:
            return {
                "status": "error",
                "content": f"HTTP {response.status_code}: {response.text[:200]}",
                "latency": latency,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
            
    except requests.Timeout:
        return {
            "status": "timeout",
            "content": f"Timeout sau {timeout}s",
            "latency": timeout,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    except Exception as e:
        return {
            "status": "error",
            "content": str(e),
            "latency": time.time() - start_time,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }


# ══════════════════════════════════════════════════
# HÀM CHẤM ĐIỂM TỰ ĐỘNG
# ══════════════════════════════════════════════════

def score_response(response_text: str, expected_keywords: list) -> dict:
    """Chấm điểm tự động dựa trên keyword matching."""
    if not response_text:
        return {"keyword_hits": 0, "total_keywords": len(expected_keywords), "score": 0.0, "matched": []}
    
    text_lower = response_text.lower()
    matched = []
    for kw in expected_keywords:
        if kw.lower() in text_lower:
            matched.append(kw)
    
    hit_count = len(matched)
    total = len(expected_keywords)
    score = (hit_count / total * 100) if total > 0 else 0.0
    
    return {
        "keyword_hits": hit_count,
        "total_keywords": total,
        "score": round(score, 1),
        "matched": matched
    }


def detect_hallucination(response_text: str) -> dict:
    """Phát hiện dấu hiệu ảo giác (hallucination) trong câu trả lời."""
    text_lower = response_text.lower()
    
    red_flags = []
    
    # 1. Check viện dẫn luật sai / không tồn tại
    fake_law_patterns = [
        "luật hôn nhân 2000",  # Luật cũ đã hết hiệu lực
        "luật lao động 2012",  # Sai năm
        "bộ luật dân sự 2005 sửa đổi",  # Không chính xác
    ]
    for fp in fake_law_patterns:
        if fp in text_lower:
            red_flags.append(f"Viện dẫn luật cũ/sai: '{fp}'")
    
    # 2. Check nội dung bịa đặt rõ ràng
    fiction_markers = [
        "theo luật liên bang",
        "theo hiến pháp hoa kỳ",
        "theo pháp luật mỹ",
        "theo bộ luật dân sự pháp",
    ]
    for fm in fiction_markers:
        if fm in text_lower:
            red_flags.append(f"Viện dẫn luật nước ngoài: '{fm}'")
    
    # 3. Check hội chứng "tôi chắc chắn" nhưng sai
    confidence_but_vague = (
        "chắc chắn" in text_lower and 
        len(response_text) < 100
    )
    if confidence_but_vague:
        red_flags.append("Quá tự tin nhưng câu trả lời quá ngắn")
    
    return {
        "has_hallucination_flags": len(red_flags) > 0,
        "flags": red_flags,
        "flag_count": len(red_flags)
    }


# ══════════════════════════════════════════════════
# MAIN BENCHMARK RUNNER
# ══════════════════════════════════════════════════

def run_benchmark():
    print("=" * 80)
    print("🧪 BENCHMARK: So sánh 3 LLM Models trên FPT Cloud")
    print("   Đánh giá khả năng tư duy pháp lý Việt Nam")
    print("=" * 80)
    print(f"⏰ Bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔑 API Key: {FPT_API_KEY[:15]}...{FPT_API_KEY[-5:]}")
    print(f"📋 Số câu hỏi: {len(LEGAL_QUESTIONS)}")
    print(f"🤖 Models: {', '.join(MODELS.keys())}")
    print()
    
    # Kiểm tra kết nối nhanh
    print("🔌 Kiểm tra kết nối API FPT Cloud...")
    test_result = call_fpt_model("gemma-4-31B-it", "Xin chào", timeout=15)
    if test_result["status"] != "success":
        print(f"❌ Không thể kết nối FPT Cloud: {test_result['content']}")
        print("   Kiểm tra lại API Key và kết nối mạng.")
        sys.exit(1)
    print(f"✅ Kết nối thành công! (Latency: {test_result['latency']:.2f}s)")
    print()
    
    # ── Chạy benchmark ──
    all_results = {}
    model_scores = {model: {"total_score": 0, "total_latency": 0, "total_tokens": 0, 
                             "success_count": 0, "hallucination_count": 0}
                    for model in MODELS}
    
    for q_idx, question in enumerate(LEGAL_QUESTIONS):
        qid = question["id"]
        print(f"{'─' * 80}")
        print(f"📝 [{qid}] {question['category']} | Độ khó: {question['difficulty']}")
        print(f"   ❓ {question['question']}")
        print()
        
        all_results[qid] = {}
        
        for model_key, model_info in MODELS.items():
            emoji = model_info["emoji"]
            name = model_info["name"]
            
            print(f"   {emoji} Đang hỏi {name}...", end=" ", flush=True)
            
            result = call_fpt_model(model_key, question["question"], timeout=60)
            
            if result["status"] == "success":
                # Chấm điểm
                scoring = score_response(result["content"], question["expected_keywords"])
                halluc = detect_hallucination(result["content"])
                
                print(f"✅ {result['latency']:.1f}s | Score: {scoring['score']}% | "
                      f"Tokens: {result['total_tokens']}")
                
                # Cập nhật tổng kết
                model_scores[model_key]["total_score"] += scoring["score"]
                model_scores[model_key]["total_latency"] += result["latency"]
                model_scores[model_key]["total_tokens"] += result["total_tokens"]
                model_scores[model_key]["success_count"] += 1
                if halluc["has_hallucination_flags"]:
                    model_scores[model_key]["hallucination_count"] += 1
                
                all_results[qid][model_key] = {
                    "content": result["content"],
                    "latency": result["latency"],
                    "tokens": result["total_tokens"],
                    "scoring": scoring,
                    "hallucination": halluc
                }
                
                # In trích đoạn câu trả lời (100 ký tự đầu)
                snippet = result["content"][:150].replace("\n", " ")
                print(f"      📄 \"{snippet}...\"")
                
                if halluc["has_hallucination_flags"]:
                    print(f"      ⚠️ CẢNH BÁO ẢO GIÁC: {halluc['flags']}")
                    
            else:
                print(f"❌ {result['status']}: {result['content'][:100]}")
                all_results[qid][model_key] = {
                    "content": result["content"],
                    "latency": result["latency"],
                    "tokens": 0,
                    "scoring": {"score": 0, "keyword_hits": 0, "total_keywords": len(question["expected_keywords"]), "matched": []},
                    "hallucination": {"has_hallucination_flags": False, "flags": [], "flag_count": 0}
                }
            
            print()
    
    # ══════════════════════════════════════════════════
    # BẢNG TỔNG KẾT
    # ══════════════════════════════════════════════════
    
    print()
    print("=" * 80)
    print("📊 BẢNG TỔNG KẾT BENCHMARK")
    print("=" * 80)
    
    n_questions = len(LEGAL_QUESTIONS)
    
    print(f"\n{'Model':<35} {'Avg Score':>10} {'Avg Latency':>12} {'Avg Tokens':>12} {'Halluc':>8} {'Success':>8}")
    print("─" * 85)
    
    ranking = []
    for model_key, stats in model_scores.items():
        info = MODELS[model_key]
        success = stats["success_count"]
        avg_score = stats["total_score"] / success if success > 0 else 0
        avg_latency = stats["total_latency"] / success if success > 0 else 0
        avg_tokens = stats["total_tokens"] / success if success > 0 else 0
        halluc = stats["hallucination_count"]
        
        ranking.append({
            "model": model_key,
            "name": info["name"],
            "emoji": info["emoji"],
            "avg_score": avg_score,
            "avg_latency": avg_latency,
            "avg_tokens": avg_tokens,
            "halluc_count": halluc,
            "success_count": success
        })
        
        print(f"{info['emoji']} {info['name']:<33} {avg_score:>9.1f}% {avg_latency:>10.1f}s {avg_tokens:>11.0f} {halluc:>7} {success:>5}/{n_questions}")
    
    # Sắp xếp theo điểm cao nhất
    ranking.sort(key=lambda x: x["avg_score"], reverse=True)
    
    print()
    print("🏆 XẾP HẠNG TỔNG HỢP:")
    print("─" * 50)
    for rank, r in enumerate(ranking):
        medal = ["🥇", "🥈", "🥉"][rank] if rank < 3 else f"#{rank+1}"
        print(f"  {medal} {r['emoji']} {r['name']}")
        print(f"     Score: {r['avg_score']:.1f}% | Latency: {r['avg_latency']:.1f}s | Ảo giác: {r['halluc_count']}")
    
    # ══════════════════════════════════════════════════
    # CHI TIẾT TỪNG CÂU HỎI
    # ══════════════════════════════════════════════════
    
    print()
    print("=" * 80)
    print("📋 CHI TIẾT SO SÁNH TỪNG CÂU HỎI")
    print("=" * 80)
    
    for question in LEGAL_QUESTIONS:
        qid = question["id"]
        print(f"\n{'─' * 70}")
        print(f"[{qid}] {question['question']}")
        print(f"Keywords kỳ vọng: {question['expected_keywords']}")
        print()
        
        if qid in all_results:
            for model_key in MODELS:
                if model_key in all_results[qid]:
                    r = all_results[qid][model_key]
                    emoji = MODELS[model_key]["emoji"]
                    name = MODELS[model_key]["name"]
                    
                    print(f"  {emoji} {name} (Score: {r['scoring']['score']}% | {r['latency']:.1f}s)")
                    print(f"     Matched: {r['scoring']['matched']}")
                    
                    # In câu trả lời đầy đủ
                    content_lines = r["content"].split("\n")
                    for line in content_lines[:8]:  # Chỉ hiện 8 dòng đầu
                        print(f"     │ {line}")
                    if len(content_lines) > 8:
                        print(f"     │ ... (còn {len(content_lines) - 8} dòng)")
                    print()
    
    # ══════════════════════════════════════════════════
    # LƯU KẾT QUẢ RA FILE JSON
    # ══════════════════════════════════════════════════
    
    output_file = "scratch/benchmark_llm_results.json"
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "models": MODELS,
        "questions": LEGAL_QUESTIONS,
        "results": {},
        "summary": {}
    }
    
    # Convert results for JSON serialization
    for qid, model_results in all_results.items():
        output_data["results"][qid] = {}
        for model_key, r in model_results.items():
            output_data["results"][qid][model_key] = {
                "content": r["content"],
                "latency": round(r["latency"], 3),
                "tokens": r["tokens"],
                "score": r["scoring"]["score"],
                "matched_keywords": r["scoring"]["matched"],
                "hallucination_flags": r["hallucination"]["flags"]
            }
    
    # Summary
    for r in ranking:
        output_data["summary"][r["model"]] = {
            "name": r["name"],
            "avg_score": round(r["avg_score"], 1),
            "avg_latency": round(r["avg_latency"], 2),
            "avg_tokens": round(r["avg_tokens"], 0),
            "hallucination_count": r["halluc_count"],
            "success_count": r["success_count"]
        }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Kết quả chi tiết đã lưu vào: {output_file}")
    print(f"⏰ Hoàn thành: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
