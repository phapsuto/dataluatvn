"""
Benchmark 100 câu THỰC TẾ — câu hỏi người dùng thật hay hỏi
V21 SQ8 + Reranker ON + Router Fix
"""
import requests, time, json, random, subprocess

API = 'http://localhost:8000/assistant/chat'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': 'dlvn_testkey'}

def get_ram_mb():
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'uvicorn server:app' in line and 'grep' not in line:
                return int(line.split()[5]) / 1024
    except:
        pass
    return 0

# ═══════════════════════════════════════════════════════════════
# 100 CÂU HỎI THỰC TẾ — người dùng thật hay hỏi
# ═══════════════════════════════════════════════════════════════

REALISTIC_QUESTIONS = [
    # ─── ĐẤT ĐAI (20 câu) ───
    {"q": "Điều kiện để được cấp sổ đỏ cho đất không có giấy tờ là gì?", "type": "C"},
    {"q": "Thủ tục tách thửa đất theo Luật Đất đai 2024 như thế nào?", "type": "C"},
    {"q": "Cách tính giá bồi thường khi Nhà nước thu hồi đất hiện nay?", "type": "C"},
    {"q": "Tôi muốn sang tên sổ đỏ cho con, cần làm thủ tục gì?", "type": "E"},
    {"q": "Đất nông nghiệp có được chuyển đổi mục đích sang đất ở không?", "type": "E"},
    {"q": "Hàng xóm lấn chiếm đất của tôi, tôi phải làm gì?", "type": "E"},
    {"q": "Diện tích tối thiểu để tách thửa đất ở là bao nhiêu?", "type": "C"},
    {"q": "Thời hạn sử dụng đất nông nghiệp là bao lâu?", "type": "C"},
    {"q": "Quyền của người sử dụng đất theo Luật Đất đai 2024", "type": "C"},
    {"q": "Đất do ông bà để lại nhưng không có di chúc thì chia như thế nào?", "type": "E"},
    {"q": "Điều 5 Luật Đất đai 2024 quy định nội dung gì?", "type": "B"},
    {"q": "Nội dung chính của Nghị định 88/2024/NĐ-CP về bồi thường khi thu hồi đất", "type": "D"},
    {"q": "Tôi mua đất bằng giấy viết tay có được pháp luật công nhận không?", "type": "E"},
    {"q": "Luật Đất đai 2024 có gì mới so với Luật 2013?", "type": "C"},
    {"q": "Người nước ngoài có được mua đất ở Việt Nam không?", "type": "E"},
    {"q": "Quy định về đấu giá quyền sử dụng đất hiện nay", "type": "C"},
    {"q": "Đất tranh chấp đang kiện thì có được xây nhà không?", "type": "E"},
    {"q": "Thu hồi đất để làm dự án, người dân có quyền từ chối không?", "type": "E"},
    {"q": "Điều 79 Luật Đất đai 2024 quy định về thu hồi đất như thế nào?", "type": "B"},
    {"q": "Cho tôi nội dung Nghị định 102/2024/NĐ-CP", "type": "D"},
    
    # ─── LAO ĐỘNG (20 câu) ───
    {"q": "Người lao động nghỉ việc cần báo trước bao nhiêu ngày?",  "type": "C"},
    {"q": "Cách tính trợ cấp thôi việc theo Bộ luật Lao động", "type": "C"},
    {"q": "Công ty nợ lương 3 tháng, tôi có quyền đơn phương nghỉ việc không?", "type": "E"},
    {"q": "Lương thử việc tối thiểu bằng bao nhiêu phần trăm lương chính thức?", "type": "C"},
    {"q": "Điều 36 Bộ luật Lao động 2019 quy định về vấn đề gì?", "type": "B"},
    {"q": "Người lao động bị tai nạn lao động được hưởng chế độ gì?", "type": "E"},
    {"q": "Số ngày nghỉ phép năm theo quy định hiện hành là bao nhiêu?", "type": "C"},
    {"q": "Công ty sa thải tôi không có lý do, tôi phải làm gì?",  "type": "E"},
    {"q": "Quy định về làm thêm giờ tối đa trong tháng", "type": "C"},
    {"q": "Chế độ thai sản cho lao động nữ theo quy định hiện hành", "type": "C"},
    {"q": "Tuổi nghỉ hưu năm 2025 là bao nhiêu tuổi?", "type": "E"},
    {"q": "Người lao động có quyền đình công không và điều kiện là gì?", "type": "C"},
    {"q": "Cho tôi nội dung Nghị định 145/2020/NĐ-CP hướng dẫn Bộ luật Lao động", "type": "D"},
    {"q": "Hợp đồng lao động có bắt buộc phải bằng văn bản không?", "type": "E"},
    {"q": "Quy định về bảo hiểm xã hội bắt buộc cho người lao động", "type": "C"},
    {"q": "Công ty phá sản, quyền lợi người lao động được giải quyết thế nào?", "type": "E"},
    {"q": "Điều 5 Bộ luật Lao động 2019 quy định gì?", "type": "B"},
    {"q": "Nội dung Thông tư 10/2020/TT-BLĐTBXH", "type": "D"},
    {"q": "Mức lương tối thiểu vùng áp dụng từ 2024 là bao nhiêu?", "type": "C"},
    {"q": "Lao động nước ngoài làm việc tại Việt Nam cần giấy phép gì?", "type": "E"},

    # ─── HÔN NHÂN GIA ĐÌNH (15 câu) ───
    {"q": "Thủ tục ly hôn thuận tình theo quy định hiện hành", "type": "C"},
    {"q": "Tài sản chung vợ chồng được phân chia khi ly hôn như thế nào?", "type": "C"},
    {"q": "Quyền nuôi con sau ly hôn được xác định dựa trên tiêu chí gì?", "type": "C"},
    {"q": "Chồng tôi ngoại tình, tôi có quyền kiện không?", "type": "E"},
    {"q": "Nghĩa vụ cấp dưỡng nuôi con sau ly hôn theo quy định", "type": "C"},
    {"q": "Nam nữ sống chung không đăng ký kết hôn thì pháp luật quy định thế nào?", "type": "E"},
    {"q": "Độ tuổi kết hôn theo quy định của pháp luật Việt Nam", "type": "C"},
    {"q": "Điều 21 Luật Hôn nhân và Gia đình 2014 quy định gì?", "type": "B"},
    {"q": "Bạo lực gia đình bị xử phạt như thế nào?", "type": "E"},
    {"q": "Cho tôi nội dung Luật Hôn nhân và Gia đình 2014 số 52/2014/QH13", "type": "D"},
    {"q": "Vợ chồng có tài sản riêng trước hôn nhân thì xử lý ra sao khi ly hôn?", "type": "E"},
    {"q": "Quy định về nhận nuôi con nuôi theo pháp luật Việt Nam", "type": "C"},
    {"q": "Thủ tục đăng ký kết hôn với người nước ngoài tại Việt Nam", "type": "E"},
    {"q": "Quyền thừa kế của con ngoài giá thú theo pháp luật", "type": "C"},
    {"q": "Mẹ tôi bị chồng đánh, làm cách nào để bảo vệ mẹ theo pháp luật?", "type": "E"},

    # ─── HÌNH SỰ + HÀNH CHÍNH (15 câu) ───
    {"q": "Vượt đèn đỏ bị phạt bao nhiêu tiền theo Nghị định 168?", "type": "E"},
    {"q": "Quy định mức phạt nồng độ cồn khi lái xe năm 2024", "type": "C"},
    {"q": "Tội trộm cắp tài sản bị xử phạt thế nào theo Bộ luật Hình sự?", "type": "C"},
    {"q": "Cho tôi nội dung Nghị định 168/2024/NĐ-CP về xử phạt giao thông", "type": "D"},
    {"q": "Bị hàng xóm đánh gây thương tích, tôi khởi kiện ở đâu?", "type": "E"},
    {"q": "Điều 134 Bộ luật Hình sự 2015 quy định về tội gì?", "type": "B"},
    {"q": "Tuổi chịu trách nhiệm hình sự theo quy định hiện hành", "type": "C"},
    {"q": "Thời hiệu truy cứu trách nhiệm hình sự là bao lâu?", "type": "C"},
    {"q": "Buôn bán hàng giả bị xử lý như thế nào?", "type": "E"},
    {"q": "Đánh bạc bị phạt hành chính hay xử lý hình sự?", "type": "E"},
    {"q": "Quy định về tạm giam, tạm giữ trong tố tụng hình sự", "type": "C"},
    {"q": "Cho vay nặng lãi có bị truy cứu hình sự không?", "type": "E"},
    {"q": "Điều 321 Bộ luật Hình sự 2015 về tội đánh bạc", "type": "B"},
    {"q": "Nội dung chính Bộ luật Hình sự năm 2015 số 100/2015/QH13", "type": "D"},
    {"q": "Tôi bị lừa đảo qua mạng, trình báo ở đâu và quy trình xử lý?", "type": "E"},

    # ─── DOANH NGHIỆP + THUẾ (15 câu) ───
    {"q": "Thủ tục thành lập công ty TNHH một thành viên", "type": "C"},
    {"q": "Các loại thuế doanh nghiệp phải nộp theo quy định", "type": "C"},
    {"q": "Cho tôi nội dung Luật Doanh nghiệp 2020 số 59/2020/QH14", "type": "D"},
    {"q": "Điều 46 Luật Doanh nghiệp 2020 quy định nội dung gì?", "type": "B"},
    {"q": "Công ty tôi muốn giải thể, thủ tục ra sao?", "type": "E"},
    {"q": "Quy định về hóa đơn điện tử theo Nghị định 123/2020/NĐ-CP", "type": "C"},
    {"q": "Cho tôi nội dung Nghị định 123/2020/NĐ-CP về hóa đơn chứng từ", "type": "D"},
    {"q": "Thuế thu nhập cá nhân được tính như thế nào?", "type": "C"},
    {"q": "Thủ tục đăng ký kinh doanh hộ cá thể", "type": "C"},
    {"q": "Quy định xử phạt khi trốn thuế theo pháp luật", "type": "C"},
    {"q": "Doanh nghiệp không đóng bảo hiểm cho nhân viên bị phạt thế nào?", "type": "E"},
    {"q": "Điều kiện để được hưởng ưu đãi thuế thu nhập doanh nghiệp", "type": "C"},
    {"q": "Vốn điều lệ tối thiểu để thành lập công ty là bao nhiêu?", "type": "E"},
    {"q": "Quy định về bảo vệ quyền lợi người tiêu dùng hiện hành", "type": "C"},
    {"q": "Điều 3 Luật Thuế thu nhập doanh nghiệp quy định gì?", "type": "B"},

    # ─── SỐ HIỆU CỤ THỂ BỔ SUNG (D-type, 5 câu) ───
    {"q": "Cho tôi nội dung Luật Nhà ở 2023 số 27/2023/QH15", "type": "D"},
    {"q": "Nội dung chính của Nghị định 100/2019/NĐ-CP về xử phạt giao thông", "type": "D"},
    {"q": "Cho tôi biết nội dung Luật Bảo vệ môi trường 2020 số 72/2020/QH14", "type": "D"},
    {"q": "Điều 12 Luật Nhà ở 2023 quy định nội dung gì?", "type": "B"},
    {"q": "Điều 155 Bộ luật Hình sự 2015 quy định về tội gì?", "type": "B"},
]

def run_benchmark():
    print("=" * 70)
    print("📊 BENCHMARK 100 CÂU THỰC TẾ — V21 SQ8")  
    print("=" * 70)
    
    ram_before = get_ram_mb()
    print(f"💾 RAM: {ram_before:.0f} MB")
    
    questions = REALISTIC_QUESTIONS.copy()
    random.shuffle(questions)
    print(f"📝 Tổng: {len(questions)} câu (B={sum(1 for q in questions if q['type']=='B')}, C={sum(1 for q in questions if q['type']=='C')}, D={sum(1 for q in questions if q['type']=='D')}, E={sum(1 for q in questions if q['type']=='E')})")
    
    results = {'B': [], 'C': [], 'D': [], 'E': []}
    latencies = []
    
    for i, q in enumerate(questions):
        start = time.time()
        try:
            r = requests.post(API, json={
                'prompt': q['q'],
                'session_id': f'real_{i}'
            }, headers=HEADERS, timeout=180)
            lat = time.time() - start
            latencies.append(lat)
            
            data = r.json()
            resp = data.get('response', '')
            cits = data.get('citations', [])
            
            # Đánh giá: có trả lời có ý nghĩa + có citation
            # Clarification responses (câu hỏi gợi mở) cũng tính là valid
            is_clarification = '1️⃣' in resp or 'cho biết thêm' in resp.lower()
            has_useful_response = (len(resp) > 80 and len(cits) > 0) or is_clarification
            # Không trả "ngoài phạm vi"  
            not_refused = 'ngoài phạm vi' not in resp.lower() and 'không thể trả lời' not in resp.lower()
            
            correct = has_useful_response and not_refused
            status = '✅' if correct else '❌'
            
            results[q['type']].append({
                'correct': correct,
                'latency': lat,
                'resp_len': len(resp),
                'cit_count': len(cits),
                'query': q['q'][:50]
            })
            
            # Print mỗi 5 câu + failures
            if (i + 1) % 5 == 0 or not correct:
                print(f"[{i+1:3d}/{len(questions)}] {status} {lat:5.1f}s | {q['type']} | cits={len(cits)} | {q['q'][:50]}...")
                
        except Exception as e:
            lat = time.time() - start
            print(f"[{i+1:3d}] 💥 {lat:5.1f}s | ERROR: {str(e)[:40]}")
            results[q['type']].append({'correct': False, 'latency': lat, 'resp_len': 0, 'cit_count': 0, 'query': q['q'][:50]})
    
    ram_after = get_ram_mb()
    
    print("\n" + "=" * 70)
    print("📊 KẾT QUẢ V21 — 100 CÂU THỰC TẾ")
    print("=" * 70)
    
    total_correct = 0
    total_q = 0
    for t in ['B', 'C', 'D', 'E']:
        items = results[t]
        if not items:
            continue
        c = sum(1 for x in items if x['correct'])
        n = len(items)
        total_correct += c
        total_q += n
        avg = sum(x['latency'] for x in items) / n
        print(f"  {t}: {c}/{n} = {c/n*100:.1f}% | avg {avg:.1f}s")
        
        # In failures
        failures = [x for x in items if not x['correct']]
        if failures:
            for f in failures[:3]:
                print(f"    ❌ {f['query']}... (cits={f['cit_count']}, len={f['resp_len']})")
    
    avg_lat = sum(latencies)/len(latencies) if latencies else 0
    p95 = sorted(latencies)[int(0.95*len(latencies))] if latencies else 0
    print(f"\n  ══ TOTAL: {total_correct}/{total_q} = {total_correct/total_q*100:.1f}% ══")
    print(f"  Avg Latency: {avg_lat:.1f}s | P95: {p95:.1f}s")
    print(f"  💾 RAM: {ram_after:.0f} MB | ⏱️ Total: {sum(latencies)/60:.1f} min")

if __name__ == '__main__':
    run_benchmark()
