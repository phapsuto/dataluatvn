"""
DataLuatVN — Benchmark Test 100 câu hỏi pháp luật
Gọi API /assistant/chat và đánh giá chất lượng trả lời.

Cách chạy:
    python tests/benchmark_chatbot.py

Output: File CSV kết quả + báo cáo tổng hợp console.
"""

import requests
import json
import time
import csv
import re
import os
from datetime import datetime

# ─── CONFIG ───
BASE_URL = "http://localhost:2004"
API_KEY = "dlvn_portal_default_key"
OUTPUT_DIR = "tests/benchmark_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── 100 CÂU HỎI PHÁP LUẬT VIỆT NAM ───
# Chia theo lĩnh vực, mỗi câu có expected_domain và expected_keywords (từ khóa kỳ vọng trong câu trả lời)

QUESTIONS = [
    # ═══════════════════════════════════════════
    # HÌNH SỰ (15 câu)
    # ═══════════════════════════════════════════
    {"id": 1, "domain": "hinh_su", "question": "Tội giết người theo Điều 123 Bộ luật Hình sự 2015 bị phạt như thế nào?",
     "keywords": ["Điều 123", "tù", "chung thân", "tử hình"]},
    {"id": 2, "domain": "hinh_su", "question": "Người chưa thành niên từ đủ 14 tuổi đến dưới 16 tuổi phải chịu trách nhiệm hình sự về những tội gì?",
     "keywords": ["14 tuổi", "16 tuổi", "rất nghiêm trọng", "đặc biệt nghiêm trọng"]},
    {"id": 3, "domain": "hinh_su", "question": "Thế nào là phòng vệ chính đáng theo pháp luật hình sự Việt Nam?",
     "keywords": ["phòng vệ", "chính đáng", "xâm phạm", "cần thiết"]},
    {"id": 4, "domain": "hinh_su", "question": "Tội trộm cắp tài sản theo Điều 173 BLHS 2015 quy định thế nào?",
     "keywords": ["Điều 173", "trộm cắp", "triệu đồng"]},
    {"id": 5, "domain": "hinh_su", "question": "Các tình tiết giảm nhẹ trách nhiệm hình sự được quy định tại điều nào?",
     "keywords": ["giảm nhẹ", "Điều 51"]},
    {"id": 6, "domain": "hinh_su", "question": "Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác quy định thế nào?",
     "keywords": ["thương tích", "tổn hại", "sức khỏe", "Điều 134"]},
    {"id": 7, "domain": "hinh_su", "question": "Án treo là gì? Điều kiện được hưởng án treo theo BLHS 2015?",
     "keywords": ["án treo", "thử thách", "Điều 65"]},
    {"id": 8, "domain": "hinh_su", "question": "Tội lừa đảo chiếm đoạt tài sản bị xử phạt như thế nào?",
     "keywords": ["lừa đảo", "chiếm đoạt", "Điều 174"]},
    {"id": 9, "domain": "hinh_su", "question": "Quy định về đồng phạm trong Bộ luật Hình sự 2015 như thế nào?",
     "keywords": ["đồng phạm", "Điều 17", "tổ chức", "xúi giục", "giúp sức"]},
    {"id": 10, "domain": "hinh_su", "question": "Tội tàng trữ, vận chuyển, mua bán trái phép chất ma túy bị xử phạt ra sao?",
     "keywords": ["ma túy", "tàng trữ", "Điều 249", "Điều 250", "Điều 251"]},
    {"id": 11, "domain": "hinh_su", "question": "Thời hiệu truy cứu trách nhiệm hình sự là bao lâu?",
     "keywords": ["thời hiệu", "truy cứu", "Điều 27"]},
    {"id": 12, "domain": "hinh_su", "question": "Tội vi phạm quy định về tham gia giao thông đường bộ quy định thế nào?",
     "keywords": ["giao thông", "Điều 260"]},
    {"id": 13, "domain": "hinh_su", "question": "Quy định về tội hiếp dâm trong BLHS 2015 như thế nào?",
     "keywords": ["hiếp dâm", "Điều 141"]},
    {"id": 14, "domain": "hinh_su", "question": "Tội hủy hoại tài sản theo Điều 178 BLHS 2015 có khung hình phạt ra sao?",
     "keywords": ["hủy hoại", "Điều 178", "cố ý"]},
    {"id": 15, "domain": "hinh_su", "question": "A 17 tuổi phạm tội cố ý làm hư hỏng tài sản theo khoản 1 Điều 178 BLHS có khung phạt tiền từ 10 đến 50 triệu. Nếu Tòa áp dụng phạt tiền là hình phạt chính thì mức tối đa A phải chịu là bao nhiêu?",
     "keywords": ["chưa thành niên", "1/2", "một phần hai", "25 triệu", "Điều 99", "Điều 100"]},

    # ═══════════════════════════════════════════
    # DÂN SỰ / HÔN NHÂN GIA ĐÌNH (15 câu)
    # ═══════════════════════════════════════════
    {"id": 16, "domain": "dan_su", "question": "Điều kiện kết hôn theo Luật Hôn nhân và Gia đình 2014 là gì?",
     "keywords": ["kết hôn", "18 tuổi", "20 tuổi", "tự nguyện"]},
    {"id": 17, "domain": "dan_su", "question": "Thủ tục ly hôn đơn phương được quy định như thế nào?",
     "keywords": ["ly hôn", "đơn phương", "Tòa án"]},
    {"id": 18, "domain": "dan_su", "question": "Quyền nuôi con sau ly hôn được pháp luật quy định ra sao?",
     "keywords": ["nuôi con", "ly hôn", "36 tháng", "3 tuổi"]},
    {"id": 19, "domain": "dan_su", "question": "Di chúc hợp pháp cần đáp ứng những điều kiện gì?",
     "keywords": ["di chúc", "hợp pháp", "minh mẫn", "tự nguyện"]},
    {"id": 20, "domain": "dan_su", "question": "Hàng thừa kế theo pháp luật được chia như thế nào?",
     "keywords": ["thừa kế", "hàng thứ nhất", "hàng thứ hai", "hàng thứ ba"]},
    {"id": 21, "domain": "dan_su", "question": "Hợp đồng dân sự vô hiệu trong trường hợp nào?",
     "keywords": ["vô hiệu", "hợp đồng", "giả tạo", "bị lừa dối"]},
    {"id": 22, "domain": "dan_su", "question": "Bồi thường thiệt hại ngoài hợp đồng được quy định thế nào trong BLDS 2015?",
     "keywords": ["bồi thường", "thiệt hại", "ngoài hợp đồng", "Điều 584"]},
    {"id": 23, "domain": "dan_su", "question": "Quyền sở hữu tài sản chung của vợ chồng theo Luật Hôn nhân và Gia đình?",
     "keywords": ["tài sản chung", "vợ chồng", "trong thời kỳ hôn nhân"]},
    {"id": 24, "domain": "dan_su", "question": "Thời hiệu khởi kiện vụ án dân sự là bao lâu?",
     "keywords": ["thời hiệu", "khởi kiện", "3 năm", "Điều 429"]},
    {"id": 25, "domain": "dan_su", "question": "Hợp đồng đặt cọc mua bán nhà đất có hiệu lực khi nào?",
     "keywords": ["đặt cọc", "nhà đất", "giao kết"]},
    {"id": 26, "domain": "dan_su", "question": "Thế nào là hợp đồng ủy quyền? Quy định pháp luật về ủy quyền?",
     "keywords": ["ủy quyền", "đại diện", "Điều 562"]},
    {"id": 27, "domain": "dan_su", "question": "Quyền thừa kế của con nuôi theo pháp luật Việt Nam?",
     "keywords": ["con nuôi", "thừa kế", "hàng thứ nhất"]},
    {"id": 28, "domain": "dan_su", "question": "Người bị hạn chế năng lực hành vi dân sự là gì?",
     "keywords": ["hạn chế", "năng lực hành vi", "nghiện", "Điều 24"]},
    {"id": 29, "domain": "dan_su", "question": "Quy định về quyền nhân thân trong Bộ luật Dân sự 2015?",
     "keywords": ["quyền nhân thân", "bất khả xâm phạm", "không thể chuyển giao"]},
    {"id": 30, "domain": "dan_su", "question": "Trách nhiệm bồi thường thiệt hại do nguồn nguy hiểm cao độ gây ra?",
     "keywords": ["nguồn nguy hiểm cao độ", "bồi thường", "Điều 601"]},

    # ═══════════════════════════════════════════
    # LAO ĐỘNG (15 câu)
    # ═══════════════════════════════════════════
    {"id": 31, "domain": "lao_dong", "question": "Thời gian thử việc tối đa theo Bộ luật Lao động 2019 là bao lâu?",
     "keywords": ["thử việc", "6 tháng", "60 ngày", "30 ngày"]},
    {"id": 32, "domain": "lao_dong", "question": "Người lao động được đơn phương chấm dứt hợp đồng lao động khi nào?",
     "keywords": ["đơn phương", "chấm dứt", "Điều 35"]},
    {"id": 33, "domain": "lao_dong", "question": "Quy định về mức lương tối thiểu vùng hiện hành?",
     "keywords": ["lương tối thiểu", "vùng"]},
    {"id": 34, "domain": "lao_dong", "question": "Chế độ thai sản theo Luật Bảo hiểm xã hội quy định thế nào?",
     "keywords": ["thai sản", "6 tháng", "bảo hiểm xã hội"]},
    {"id": 35, "domain": "lao_dong", "question": "Trợ cấp thôi việc được tính như thế nào?",
     "keywords": ["trợ cấp thôi việc", "1/2 tháng lương", "Điều 46"]},
    {"id": 36, "domain": "lao_dong", "question": "Thời giờ làm việc bình thường theo Bộ luật Lao động là bao nhiêu?",
     "keywords": ["8 giờ", "48 giờ", "Điều 105"]},
    {"id": 37, "domain": "lao_dong", "question": "Quy định về làm thêm giờ theo pháp luật lao động Việt Nam?",
     "keywords": ["làm thêm giờ", "40 giờ", "200 giờ", "300 giờ"]},
    {"id": 38, "domain": "lao_dong", "question": "Hợp đồng lao động không xác định thời hạn là gì?",
     "keywords": ["không xác định thời hạn", "hợp đồng lao động"]},
    {"id": 39, "domain": "lao_dong", "question": "Người sử dụng lao động sa thải trái pháp luật phải bồi thường thế nào?",
     "keywords": ["sa thải", "trái pháp luật", "bồi thường", "Điều 41"]},
    {"id": 40, "domain": "lao_dong", "question": "Quy định về bảo hiểm xã hội bắt buộc cho người lao động?",
     "keywords": ["bảo hiểm xã hội", "bắt buộc"]},
    {"id": 41, "domain": "lao_dong", "question": "Ngày nghỉ phép hàng năm của người lao động là bao nhiêu ngày?",
     "keywords": ["nghỉ phép", "12 ngày", "14 ngày", "16 ngày"]},
    {"id": 42, "domain": "lao_dong", "question": "Kỷ luật lao động bằng hình thức sa thải áp dụng trong trường hợp nào?",
     "keywords": ["kỷ luật", "sa thải", "Điều 125"]},
    {"id": 43, "domain": "lao_dong", "question": "Tuổi nghỉ hưu theo quy định mới nhất của pháp luật Việt Nam?",
     "keywords": ["nghỉ hưu", "60 tuổi", "62 tuổi", "55 tuổi"]},
    {"id": 44, "domain": "lao_dong", "question": "Quyền thành lập công đoàn cơ sở tại doanh nghiệp?",
     "keywords": ["công đoàn", "cơ sở", "thành lập"]},
    {"id": 45, "domain": "lao_dong", "question": "Quy định về tai nạn lao động và bệnh nghề nghiệp?",
     "keywords": ["tai nạn lao động", "bệnh nghề nghiệp", "bồi thường"]},

    # ═══════════════════════════════════════════
    # ĐẤT ĐAI / NHÀ Ở (15 câu)
    # ═══════════════════════════════════════════
    {"id": 46, "domain": "dat_dai", "question": "Thủ tục cấp Giấy chứng nhận quyền sử dụng đất (sổ đỏ) gồm những bước nào?",
     "keywords": ["giấy chứng nhận", "quyền sử dụng đất", "sổ đỏ"]},
    {"id": 47, "domain": "dat_dai", "question": "Điều kiện chuyển nhượng quyền sử dụng đất theo Luật Đất đai?",
     "keywords": ["chuyển nhượng", "quyền sử dụng đất"]},
    {"id": 48, "domain": "dat_dai", "question": "Khi nào Nhà nước thu hồi đất? Quy định về bồi thường khi thu hồi đất?",
     "keywords": ["thu hồi đất", "bồi thường", "giải phóng mặt bằng"]},
    {"id": 49, "domain": "dat_dai", "question": "Quy định về thời hạn sử dụng đất nông nghiệp?",
     "keywords": ["đất nông nghiệp", "thời hạn", "50 năm"]},
    {"id": 50, "domain": "dat_dai", "question": "Tranh chấp đất đai được giải quyết bằng cách nào?",
     "keywords": ["tranh chấp đất đai", "hòa giải", "Tòa án", "UBND"]},
    {"id": 51, "domain": "dat_dai", "question": "Quy định về tách thửa đất ở theo pháp luật hiện hành?",
     "keywords": ["tách thửa", "diện tích tối thiểu"]},
    {"id": 52, "domain": "dat_dai", "question": "Quyền và nghĩa vụ của người sử dụng đất theo Luật Đất đai?",
     "keywords": ["quyền", "nghĩa vụ", "người sử dụng đất"]},
    {"id": 53, "domain": "dat_dai", "question": "Đất do Nhà nước quản lý bao gồm những loại đất nào?",
     "keywords": ["Nhà nước quản lý", "loại đất"]},
    {"id": 54, "domain": "dat_dai", "question": "Quy định về cấp giấy phép xây dựng nhà ở riêng lẻ?",
     "keywords": ["giấy phép", "xây dựng", "nhà ở"]},
    {"id": 55, "domain": "dat_dai", "question": "Thuế chuyển nhượng quyền sử dụng đất hiện nay là bao nhiêu phần trăm?",
     "keywords": ["thuế", "chuyển nhượng", "2%", "phần trăm"]},
    {"id": 56, "domain": "dat_dai", "question": "Quy định về thế chấp quyền sử dụng đất tại ngân hàng?",
     "keywords": ["thế chấp", "quyền sử dụng đất", "ngân hàng"]},
    {"id": 57, "domain": "dat_dai", "question": "Người nước ngoài có được mua nhà ở tại Việt Nam không?",
     "keywords": ["người nước ngoài", "mua nhà", "sở hữu"]},
    {"id": 58, "domain": "dat_dai", "question": "Quy hoạch sử dụng đất được lập cho bao nhiêu năm?",
     "keywords": ["quy hoạch", "sử dụng đất", "10 năm"]},
    {"id": 59, "domain": "dat_dai", "question": "Quy định về quyền sử dụng đất khi vợ chồng ly hôn?",
     "keywords": ["ly hôn", "đất", "tài sản chung"]},
    {"id": 60, "domain": "dat_dai", "question": "Lệ phí trước bạ khi mua bán nhà đất là bao nhiêu?",
     "keywords": ["lệ phí trước bạ", "0.5%", "nhà đất"]},

    # ═══════════════════════════════════════════
    # DOANH NGHIỆP (15 câu)
    # ═══════════════════════════════════════════
    {"id": 61, "domain": "doanh_nghiep", "question": "Điều kiện thành lập công ty TNHH một thành viên?",
     "keywords": ["TNHH", "một thành viên", "vốn điều lệ"]},
    {"id": 62, "domain": "doanh_nghiep", "question": "So sánh công ty TNHH và công ty cổ phần?",
     "keywords": ["TNHH", "cổ phần", "thành viên", "cổ đông"]},
    {"id": 63, "domain": "doanh_nghiep", "question": "Thủ tục giải thể doanh nghiệp theo Luật Doanh nghiệp 2020?",
     "keywords": ["giải thể", "doanh nghiệp", "Điều 207", "Điều 208"]},
    {"id": 64, "domain": "doanh_nghiep", "question": "Quyền và nghĩa vụ của cổ đông phổ thông trong công ty cổ phần?",
     "keywords": ["cổ đông", "phổ thông", "quyền", "biểu quyết"]},
    {"id": 65, "domain": "doanh_nghiep", "question": "Quy định về vốn điều lệ công ty theo Luật Doanh nghiệp?",
     "keywords": ["vốn điều lệ", "góp vốn"]},
    {"id": 66, "domain": "doanh_nghiep", "question": "Thủ tục phá sản doanh nghiệp được quy định thế nào?",
     "keywords": ["phá sản", "mất khả năng thanh toán", "Tòa án"]},
    {"id": 67, "domain": "doanh_nghiep", "question": "Đại hội đồng cổ đông có những quyền hạn gì?",
     "keywords": ["đại hội đồng cổ đông", "quyền hạn", "quyết định"]},
    {"id": 68, "domain": "doanh_nghiep", "question": "Quy định về chuyển nhượng phần vốn góp trong công ty TNHH?",
     "keywords": ["chuyển nhượng", "phần vốn góp", "TNHH"]},
    {"id": 69, "domain": "doanh_nghiep", "question": "Doanh nghiệp có vốn đầu tư nước ngoài được thành lập tại Việt Nam cần điều kiện gì?",
     "keywords": ["đầu tư nước ngoài", "FDI", "giấy chứng nhận"]},
    {"id": 70, "domain": "doanh_nghiep", "question": "Hội đồng quản trị công ty cổ phần có bao nhiêu thành viên?",
     "keywords": ["hội đồng quản trị", "3 thành viên", "11 thành viên"]},
    {"id": 71, "domain": "doanh_nghiep", "question": "Quy định về doanh nghiệp xã hội theo Luật Doanh nghiệp 2020?",
     "keywords": ["doanh nghiệp xã hội", "Điều 10"]},
    {"id": 72, "domain": "doanh_nghiep", "question": "Trách nhiệm của người đại diện theo pháp luật của doanh nghiệp?",
     "keywords": ["đại diện theo pháp luật", "trách nhiệm"]},
    {"id": 73, "domain": "doanh_nghiep", "question": "Quy định về hợp đồng thương mại quốc tế?",
     "keywords": ["hợp đồng", "thương mại", "quốc tế"]},
    {"id": 74, "domain": "doanh_nghiep", "question": "Công ty hợp danh khác gì so với công ty TNHH?",
     "keywords": ["hợp danh", "trách nhiệm vô hạn", "TNHH"]},
    {"id": 75, "domain": "doanh_nghiep", "question": "Quy định về chi nhánh và văn phòng đại diện của doanh nghiệp?",
     "keywords": ["chi nhánh", "văn phòng đại diện"]},

    # ═══════════════════════════════════════════
    # HÀNH CHÍNH (15 câu)
    # ═══════════════════════════════════════════
    {"id": 76, "domain": "hanh_chinh", "question": "Mức xử phạt vi phạm hành chính tối đa trong lĩnh vực giao thông đường bộ?",
     "keywords": ["xử phạt", "giao thông", "triệu đồng"]},
    {"id": 77, "domain": "hanh_chinh", "question": "Thủ tục khiếu nại quyết định hành chính được quy định thế nào?",
     "keywords": ["khiếu nại", "quyết định hành chính", "30 ngày", "45 ngày"]},
    {"id": 78, "domain": "hanh_chinh", "question": "Quy định về đăng ký tạm trú theo Luật Cư trú 2020?",
     "keywords": ["tạm trú", "đăng ký", "cư trú"]},
    {"id": 79, "domain": "hanh_chinh", "question": "Điều kiện cấp căn cước công dân gắn chip?",
     "keywords": ["căn cước", "công dân", "gắn chip", "14 tuổi"]},
    {"id": 80, "domain": "hanh_chinh", "question": "Thuế thu nhập cá nhân đối với người có thu nhập từ tiền lương?",
     "keywords": ["thuế thu nhập cá nhân", "tiền lương", "giảm trừ"]},
    {"id": 81, "domain": "hanh_chinh", "question": "Quy định về tố cáo hành vi vi phạm pháp luật?",
     "keywords": ["tố cáo", "vi phạm pháp luật", "bảo vệ người tố cáo"]},
    {"id": 82, "domain": "hanh_chinh", "question": "Thời hạn cấp hộ chiếu phổ thông theo quy định hiện hành?",
     "keywords": ["hộ chiếu", "phổ thông", "ngày làm việc"]},
    {"id": 83, "domain": "hanh_chinh", "question": "Quy định về xử phạt vi phạm hành chính trong lĩnh vực môi trường?",
     "keywords": ["xử phạt", "môi trường", "triệu đồng"]},
    {"id": 84, "domain": "hanh_chinh", "question": "Điều kiện nhập quốc tịch Việt Nam cho người nước ngoài?",
     "keywords": ["quốc tịch", "nhập quốc tịch", "điều kiện"]},
    {"id": 85, "domain": "hanh_chinh", "question": "Quy định về biện pháp cưỡng chế thi hành quyết định xử phạt vi phạm hành chính?",
     "keywords": ["cưỡng chế", "xử phạt", "vi phạm hành chính"]},
    {"id": 86, "domain": "hanh_chinh", "question": "Thủ tục đăng ký khai sinh cho trẻ em?",
     "keywords": ["đăng ký", "khai sinh", "UBND"]},
    {"id": 87, "domain": "hanh_chinh", "question": "Quy định về giấy phép lái xe hạng B1 và B2?",
     "keywords": ["giấy phép lái xe", "B1", "B2"]},
    {"id": 88, "domain": "hanh_chinh", "question": "Mức phạt nồng độ cồn khi điều khiển xe ô tô?",
     "keywords": ["nồng độ cồn", "phạt", "ô tô", "triệu"]},
    {"id": 89, "domain": "hanh_chinh", "question": "Quy định về xử phạt vi phạm hành chính trong lĩnh vực xây dựng?",
     "keywords": ["xử phạt", "xây dựng"]},
    {"id": 90, "domain": "hanh_chinh", "question": "Thời hiệu xử phạt vi phạm hành chính là bao lâu?",
     "keywords": ["thời hiệu", "xử phạt", "1 năm", "2 năm"]},

    # ═══════════════════════════════════════════
    # TÌNH HUỐNG PHỨC TẠP (10 câu - test reasoning)
    # ═══════════════════════════════════════════
    {"id": 91, "domain": "hinh_su", "question": "A do mâu thuẫn cá nhân đã dùng dao đâm B, B tử vong trên đường đi cấp cứu. Xác định tội danh của A? Giả sử B không chết mà chỉ bị thương tật 29% thì A có phải chịu trách nhiệm hình sự không?",
     "keywords": ["giết người", "Điều 123", "cố ý gây thương tích", "Điều 134"]},
    {"id": 92, "domain": "dan_su", "question": "Ông A chết không để lại di chúc. Ông có vợ là bà B, 3 con là C, D, E. Con D đã chết trước ông A và D có 2 con là F, G. Di sản của ông A là 900 triệu. Hỏi mỗi người được hưởng bao nhiêu?",
     "keywords": ["thừa kế", "thế vị", "hàng thứ nhất", "225 triệu", "112.5 triệu"]},
    {"id": 93, "domain": "lao_dong", "question": "Chị M mang thai tháng thứ 7 nhưng công ty ra quyết định sa thải chị vì lý do 'tái cơ cấu'. Chị M có quyền gì theo pháp luật?",
     "keywords": ["mang thai", "sa thải", "không được", "Điều 37", "bồi thường"]},
    {"id": 94, "domain": "dat_dai", "question": "Anh K mua đất bằng giấy viết tay năm 2005, chưa sang tên sổ đỏ. Nay người bán đòi lại đất. Anh K có quyền gì?",
     "keywords": ["giấy viết tay", "chưa công chứng", "quyền sử dụng đất"]},
    {"id": 95, "domain": "doanh_nghiep", "question": "Công ty A có 3 cổ đông: X (60%), Y (30%), Z (10%). X và Y muốn bán toàn bộ công ty cho người ngoài. Z phản đối. Họ có bán được không?",
     "keywords": ["cổ đông", "chuyển nhượng", "biểu quyết", "65%", "phần trăm"]},
    {"id": 96, "domain": "dan_su", "question": "Bà H cho con trai một căn nhà bằng hợp đồng tặng cho có công chứng. Sau đó bà muốn lấy lại. Bà có quyền đòi lại nhà không?",
     "keywords": ["tặng cho", "công chứng", "không thể", "đã chuyển giao"]},
    {"id": 97, "domain": "hinh_su", "question": "C 13 tuổi trộm cắp điện thoại trị giá 15 triệu đồng. C có bị truy cứu trách nhiệm hình sự không? Ai phải bồi thường?",
     "keywords": ["13 tuổi", "không phải chịu", "cha mẹ", "bồi thường"]},
    {"id": 98, "domain": "hanh_chinh", "question": "Anh T bị công an phường xử phạt 5 triệu đồng vì không đội mũ bảo hiểm. Anh cho rằng mức phạt quá cao. Anh có thể khiếu nại ở đâu?",
     "keywords": ["khiếu nại", "Chủ tịch UBND", "Tòa án hành chính"]},
    {"id": 99, "domain": "lao_dong", "question": "Anh N làm việc 10 năm tại công ty, bị đơn phương chấm dứt hợp đồng trái pháp luật. Anh N được bồi thường và trợ cấp thế nào?",
     "keywords": ["10 năm", "trái pháp luật", "bồi thường", "trợ cấp thôi việc", "Điều 41"]},
    {"id": 100, "domain": "dan_su", "question": "Vợ chồng anh P ly hôn. Trong thời kỳ hôn nhân, anh P vay 500 triệu đầu tư kinh doanh riêng mà vợ không biết. Khoản nợ này ai phải trả?",
     "keywords": ["nợ riêng", "vợ không biết", "kinh doanh riêng", "tài sản riêng"]},
]


def call_chatbot(question: str, session_id: str = "benchmark") -> dict:
    """Gọi API chatbot và trả về kết quả."""
    url = f"{BASE_URL}/assistant/chat"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    payload = {
        "prompt": question,
        "session_id": session_id
    }

    start = time.time()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        latency = time.time() - start

        if resp.status_code == 200:
            data = resp.json()
            return {
                "status": "success",
                "response": data.get("response", ""),
                "citations": data.get("citations", []),
                "domain": data.get("domain", ""),
                "routing_level": data.get("routing_level", ""),
                "latency": round(latency, 2),
                "flare_activated": data.get("flare_activated", False),
            }
        else:
            return {
                "status": f"error_{resp.status_code}",
                "response": resp.text[:200],
                "citations": [],
                "domain": "",
                "routing_level": "",
                "latency": round(latency, 2),
                "flare_activated": False,
            }
    except requests.exceptions.Timeout:
        return {
            "status": "timeout",
            "response": "",
            "citations": [],
            "domain": "",
            "routing_level": "",
            "latency": 120.0,
            "flare_activated": False,
        }
    except Exception as e:
        return {
            "status": f"error: {str(e)[:100]}",
            "response": "",
            "citations": [],
            "domain": "",
            "routing_level": "",
            "latency": time.time() - start,
            "flare_activated": False,
        }


def evaluate_response(question_data: dict, result: dict) -> dict:
    """Đánh giá chất lượng câu trả lời."""
    response = result.get("response", "").lower()
    metrics = {
        "has_response": bool(response.strip()),
        "response_length": len(response),
        "has_citations": bool(re.findall(r'\[C\d+\]', result.get("response", ""))),
        "citation_count": len(re.findall(r'\[C\d+\]', result.get("response", ""))),
        "keyword_hits": 0,
        "keyword_total": len(question_data.get("keywords", [])),
        "keyword_hit_rate": 0.0,
        "is_refusal": "không tìm thấy tài liệu" in response or "không có thông tin" in response,
        "domain_match": result.get("domain", "") == question_data.get("domain", ""),
    }

    # Kiểm tra keywords
    for kw in question_data.get("keywords", []):
        if kw.lower() in response:
            metrics["keyword_hits"] += 1

    if metrics["keyword_total"] > 0:
        metrics["keyword_hit_rate"] = round(metrics["keyword_hits"] / metrics["keyword_total"], 2)

    # Quality score (0-10)
    score = 0
    if metrics["has_response"] and not metrics["is_refusal"]:
        score += 3  # Có trả lời
    if metrics["has_citations"]:
        score += 2  # Có trích dẫn
    if metrics["keyword_hit_rate"] >= 0.5:
        score += 2  # Trên 50% keywords
    if metrics["keyword_hit_rate"] >= 0.75:
        score += 1  # Trên 75% keywords
    if metrics["domain_match"]:
        score += 1  # Domain đúng
    if metrics["response_length"] > 200:
        score += 1  # Đủ chi tiết

    metrics["quality_score"] = score
    return metrics


def run_benchmark():
    """Chạy benchmark toàn bộ."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"benchmark_{timestamp}.csv")
    
    print("=" * 70)
    print(f"🚀 DATALUATVN CHATBOT BENCHMARK — {len(QUESTIONS)} câu hỏi")
    print(f"📊 Kết quả sẽ lưu tại: {csv_path}")
    print("=" * 70)

    # Kiểm tra server
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        if r.status_code != 200:
            print(f"❌ Server không phản hồi tại {BASE_URL}")
            return
    except:
        print(f"❌ Không kết nối được tới server tại {BASE_URL}. Hãy chạy 'python server.py' trước.")
        return

    results = []
    total_score = 0
    success_count = 0
    refusal_count = 0
    citation_count = 0
    domain_match_count = 0
    total_latency = 0
    domain_scores = {}

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Domain", "Question", "Status", "Response_Length",
            "Has_Citations", "Citation_Count", "Keyword_Hits", "Keyword_Total",
            "Keyword_Hit_Rate", "Domain_Match", "Is_Refusal", "Quality_Score",
            "Latency_s", "FLARE_Activated", "Response_Preview"
        ])

        for i, q in enumerate(QUESTIONS):
            qid = q["id"]
            print(f"\n[{i+1}/{len(QUESTIONS)}] Q{qid} ({q['domain']}): {q['question'][:60]}...")

            # Mỗi câu dùng session riêng để không ảnh hưởng context
            result = call_chatbot(q["question"], session_id=f"bench_{qid}")
            metrics = evaluate_response(q, result)

            # Tổng hợp
            if result["status"] == "success":
                success_count += 1
            if metrics["is_refusal"]:
                refusal_count += 1
            if metrics["has_citations"]:
                citation_count += 1
            if metrics["domain_match"]:
                domain_match_count += 1

            total_score += metrics["quality_score"]
            total_latency += result["latency"]

            # Theo domain
            d = q["domain"]
            if d not in domain_scores:
                domain_scores[d] = {"total": 0, "count": 0, "keywords_hit": 0, "keywords_total": 0}
            domain_scores[d]["total"] += metrics["quality_score"]
            domain_scores[d]["count"] += 1
            domain_scores[d]["keywords_hit"] += metrics["keyword_hits"]
            domain_scores[d]["keywords_total"] += metrics["keyword_total"]

            # Preview
            preview = result["response"][:150].replace("\n", " ") if result["response"] else ""

            writer.writerow([
                qid, q["domain"], q["question"][:100], result["status"],
                metrics["response_length"], metrics["has_citations"], metrics["citation_count"],
                metrics["keyword_hits"], metrics["keyword_total"], metrics["keyword_hit_rate"],
                metrics["domain_match"], metrics["is_refusal"], metrics["quality_score"],
                result["latency"], result["flare_activated"], preview
            ])

            # Progress
            status_icon = "✅" if metrics["quality_score"] >= 7 else ("⚠️" if metrics["quality_score"] >= 4 else "❌")
            print(f"  {status_icon} Score: {metrics['quality_score']}/10 | Keywords: {metrics['keyword_hits']}/{metrics['keyword_total']} | "
                  f"Citations: {metrics['citation_count']} | Latency: {result['latency']}s")

            # Rate limiting nhẹ
            time.sleep(1)

    # ═══════════════════════════════════════════
    # BÁO CÁO TỔNG HỢP
    # ═══════════════════════════════════════════
    n = len(QUESTIONS)
    avg_score = round(total_score / n, 2) if n > 0 else 0
    avg_latency = round(total_latency / n, 2) if n > 0 else 0

    print("\n" + "=" * 70)
    print("📊 BÁO CÁO TỔNG HỢP BENCHMARK")
    print("=" * 70)
    print(f"  📝 Tổng số câu hỏi:        {n}")
    print(f"  ✅ Trả lời thành công:      {success_count}/{n} ({round(success_count/n*100, 1)}%)")
    print(f"  ❌ Từ chối trả lời:         {refusal_count}/{n} ({round(refusal_count/n*100, 1)}%)")
    print(f"  📎 Có trích dẫn [Cx]:       {citation_count}/{n} ({round(citation_count/n*100, 1)}%)")
    print(f"  🎯 Domain phân loại đúng:   {domain_match_count}/{n} ({round(domain_match_count/n*100, 1)}%)")
    print(f"  ⭐ Điểm trung bình:         {avg_score}/10")
    print(f"  ⏱️  Latency trung bình:      {avg_latency}s")

    print(f"\n  📊 ĐIỂM THEO LĨNH VỰC:")
    print(f"  {'Lĩnh vực':<18} {'Điểm TB':>10} {'Keyword Hit':>15}")
    print(f"  {'─' * 18} {'─' * 10} {'─' * 15}")
    for d, stats in sorted(domain_scores.items()):
        avg_d = round(stats["total"] / stats["count"], 2)
        kw_rate = round(stats["keywords_hit"] / stats["keywords_total"] * 100, 1) if stats["keywords_total"] > 0 else 0
        print(f"  {d:<18} {avg_d:>8}/10 {kw_rate:>12.1f}%")

    print(f"\n  📄 Chi tiết đầy đủ: {csv_path}")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
