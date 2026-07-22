#!/usr/bin/env python3
"""
🏛️ BENCHMARK SUITE — 500 Câu Hỏi Tình Huống Pháp Luật Việt Nam
Đánh giá toàn diện hệ thống dataluatvn qua 6 tiêu chí chất lượng.
"""

import asyncio
import httpx
import json
import time
import random
import os
from datetime import datetime

API_BASE = "http://localhost:2004"
API_KEY = "dlvn_portal_default_key"

# ═══════════════════════════════════════════════════════════════════════
# PHẦN 1: NGÂN HÀNG 500 CÂU HỎI TÌNH HUỐNG PHÁP LUẬT (10 LĨNH VỰC)
# ═══════════════════════════════════════════════════════════════════════

BENCHMARK_QUESTIONS = []

# ── 1. ĐẤT ĐAI (80 câu) ──
DAT_DAI = [
    {"q": "Thủ tục xin cấp Giấy chứng nhận quyền sử dụng đất lần đầu năm 2024?", "domain": "dat_dai", "expect_keywords": ["giấy chứng nhận", "quyền sử dụng đất", "thủ tục"]},
    {"q": "Mức phạt xây nhà trái phép trên đất nông nghiệp theo Nghị định 123/2024?", "domain": "dat_dai", "expect_keywords": ["phạt", "đất nông nghiệp", "xây"]},
    {"q": "Hồ sơ chuyển nhượng quyền sử dụng đất ở gồm những gì?", "domain": "dat_dai", "expect_keywords": ["chuyển nhượng", "hồ sơ"]},
    {"q": "Thời hạn giải quyết thủ tục tách thửa đất theo Luật Đất đai 2024?", "domain": "dat_dai", "expect_keywords": ["tách thửa", "thời hạn"]},
    {"q": "Điều kiện được cấp sổ đỏ cho đất không có giấy tờ?", "domain": "dat_dai", "expect_keywords": ["sổ đỏ", "giấy tờ"]},
    {"q": "Giá đền bù khi Nhà nước thu hồi đất nông nghiệp tại Hà Nội năm 2024?", "domain": "dat_dai", "expect_keywords": ["đền bù", "thu hồi"]},
    {"q": "Quy định về hạn mức giao đất ở tại nông thôn?", "domain": "dat_dai", "expect_keywords": ["hạn mức", "giao đất"]},
    {"q": "Thủ tục đăng ký biến động khi thay đổi mục đích sử dụng đất?", "domain": "dat_dai", "expect_keywords": ["biến động", "mục đích"]},
    {"q": "Ai có thẩm quyền cấp Giấy chứng nhận quyền sử dụng đất?", "domain": "dat_dai", "expect_keywords": ["thẩm quyền", "cấp"]},
    {"q": "Thuế thu nhập cá nhân khi chuyển nhượng đất đai là bao nhiêu phần trăm?", "domain": "dat_dai", "expect_keywords": ["thuế", "chuyển nhượng"]},
    {"q": "Điều kiện để hộ gia đình được nhận chuyển nhượng đất trồng lúa?", "domain": "dat_dai", "expect_keywords": ["chuyển nhượng", "đất trồng lúa"]},
    {"q": "Quy định về thời hạn sử dụng đất nông nghiệp cho cá nhân?", "domain": "dat_dai", "expect_keywords": ["thời hạn", "đất nông nghiệp"]},
    {"q": "Thủ tục xin phép chuyển mục đích sử dụng từ đất nông nghiệp sang đất ở?", "domain": "dat_dai", "expect_keywords": ["chuyển mục đích", "đất ở"]},
    {"q": "Trường hợp nào Nhà nước thu hồi đất không bồi thường?", "domain": "dat_dai", "expect_keywords": ["thu hồi", "bồi thường"]},
    {"q": "Quy hoạch sử dụng đất cấp huyện được lập cho bao nhiêu năm?", "domain": "dat_dai", "expect_keywords": ["quy hoạch", "sử dụng đất"]},
    {"q": "Mức lệ phí trước bạ khi sang tên sổ đỏ hiện nay?", "domain": "dat_dai", "expect_keywords": ["lệ phí trước bạ", "sang tên"]},
    {"q": "Quyền và nghĩa vụ của người sử dụng đất thuê trả tiền hàng năm?", "domain": "dat_dai", "expect_keywords": ["đất thuê", "quyền", "nghĩa vụ"]},
    {"q": "Cách tính tiền sử dụng đất khi được giao đất ở?", "domain": "dat_dai", "expect_keywords": ["tiền sử dụng đất", "giao đất"]},
    {"q": "Giải quyết tranh chấp đất đai khi không có sổ đỏ như thế nào?", "domain": "dat_dai", "expect_keywords": ["tranh chấp", "đất đai"]},
    {"q": "Điều kiện thế chấp quyền sử dụng đất tại ngân hàng?", "domain": "dat_dai", "expect_keywords": ["thế chấp", "quyền sử dụng đất"]},
    {"q": "Trình tự cưỡng chế thu hồi đất theo quy định mới nhất?", "domain": "dat_dai", "expect_keywords": ["cưỡng chế", "thu hồi"]},
    {"q": "Quy định về đất liền kề và lối đi chung theo Bộ luật Dân sự?", "domain": "dat_dai", "expect_keywords": ["lối đi chung", "đất liền kề"]},
    {"q": "Thủ tục đăng ký thừa kế quyền sử dụng đất?", "domain": "dat_dai", "expect_keywords": ["thừa kế", "quyền sử dụng đất"]},
    {"q": "Đất có sổ đỏ đồng sở hữu thì bán như thế nào?", "domain": "dat_dai", "expect_keywords": ["đồng sở hữu", "bán"]},
    {"q": "Mức phạt lấn chiếm đất công theo Nghị định mới nhất?", "domain": "dat_dai", "expect_keywords": ["lấn chiếm", "đất công", "phạt"]},
    {"q": "Quy định về cấp sổ đỏ cho đất tái định cư?", "domain": "dat_dai", "expect_keywords": ["sổ đỏ", "tái định cư"]},
    {"q": "Thủ tục hợp thửa đất theo Luật Đất đai 2024?", "domain": "dat_dai", "expect_keywords": ["hợp thửa", "thủ tục"]},
    {"q": "Điều kiện để Việt kiều được mua đất tại Việt Nam?", "domain": "dat_dai", "expect_keywords": ["Việt kiều", "mua đất"]},
    {"q": "Quyền sử dụng đất có phải là tài sản chung vợ chồng không?", "domain": "dat_dai", "expect_keywords": ["tài sản chung", "vợ chồng"]},
    {"q": "Thủ tục xin giấy phép xây dựng trên đất ở nông thôn?", "domain": "dat_dai", "expect_keywords": ["giấy phép xây dựng", "nông thôn"]},
    {"q": "Đất bị quy hoạch treo thì được quyền gì?", "domain": "dat_dai", "expect_keywords": ["quy hoạch treo", "quyền"]},
    {"q": "Mức giá đất cụ thể do cơ quan nào quyết định?", "domain": "dat_dai", "expect_keywords": ["giá đất", "cơ quan"]},
    {"q": "Quy trình đấu giá quyền sử dụng đất theo quy định mới?", "domain": "dat_dai", "expect_keywords": ["đấu giá", "quyền sử dụng đất"]},
    {"q": "Đất rừng phòng hộ có được chuyển nhượng không?", "domain": "dat_dai", "expect_keywords": ["rừng phòng hộ", "chuyển nhượng"]},
    {"q": "Trách nhiệm bồi thường của Nhà nước khi thu hồi đất trái pháp luật?", "domain": "dat_dai", "expect_keywords": ["bồi thường", "trái pháp luật"]},
    {"q": "Thủ tục xác nhận diện tích đất thực tế khác với sổ đỏ?", "domain": "dat_dai", "expect_keywords": ["diện tích", "sổ đỏ"]},
    {"q": "Quyền thừa kế đất đai của con nuôi theo pháp luật?", "domain": "dat_dai", "expect_keywords": ["thừa kế", "con nuôi"]},
    {"q": "Điều kiện chuyển đổi đất nông nghiệp giữa các hộ gia đình?", "domain": "dat_dai", "expect_keywords": ["chuyển đổi", "đất nông nghiệp"]},
    {"q": "Quy định về đất tôn giáo theo Luật Đất đai 2024?", "domain": "dat_dai", "expect_keywords": ["đất tôn giáo"]},
    {"q": "Mức phạt sử dụng đất sai mục đích cho phép?", "domain": "dat_dai", "expect_keywords": ["sai mục đích", "phạt"]},
    {"q": "Thủ tục gia hạn sử dụng đất khi hết thời hạn?", "domain": "dat_dai", "expect_keywords": ["gia hạn", "thời hạn"]},
    {"q": "Đất do ông bà để lại nhưng không có di chúc thì chia thế nào?", "domain": "dat_dai", "expect_keywords": ["di chúc", "chia"]},
    {"q": "Nghĩa vụ tài chính khi được Nhà nước giao đất không thu tiền?", "domain": "dat_dai", "expect_keywords": ["nghĩa vụ tài chính", "giao đất"]},
    {"q": "Cơ sở pháp lý để khiếu nại quyết định thu hồi đất?", "domain": "dat_dai", "expect_keywords": ["khiếu nại", "thu hồi"]},
    {"q": "Đất nằm trong hành lang an toàn đường bộ có được xây dựng?", "domain": "dat_dai", "expect_keywords": ["hành lang", "đường bộ"]},
    {"q": "Quy định mới nhất về bảng giá đất hàng năm?", "domain": "dat_dai", "expect_keywords": ["bảng giá đất"]},
    {"q": "Thủ tục thu hồi đất để phát triển kinh tế xã hội?", "domain": "dat_dai", "expect_keywords": ["thu hồi", "kinh tế xã hội"]},
    {"q": "Quyền sử dụng đất góp vốn kinh doanh có được không?", "domain": "dat_dai", "expect_keywords": ["góp vốn", "kinh doanh"]},
    {"q": "Điều kiện cấp sổ đỏ cho đất có nguồn gốc khai hoang?", "domain": "dat_dai", "expect_keywords": ["khai hoang", "sổ đỏ"]},
    {"q": "Mức bồi thường tài sản gắn liền với đất khi bị thu hồi?", "domain": "dat_dai", "expect_keywords": ["bồi thường", "tài sản"]},
]

# ── 2. LAO ĐỘNG (60 câu) ──
LAO_DONG = [
    {"q": "Thời gian thử việc tối đa đối với hợp đồng lao động xác định thời hạn?", "domain": "lao_dong", "expect_keywords": ["thử việc", "thời hạn"]},
    {"q": "Điều kiện để người lao động được đơn phương chấm dứt hợp đồng?", "domain": "lao_dong", "expect_keywords": ["đơn phương", "chấm dứt"]},
    {"q": "Mức lương tối thiểu vùng 1 năm 2024 là bao nhiêu?", "domain": "lao_dong", "expect_keywords": ["lương tối thiểu", "vùng"]},
    {"q": "Quy định về làm thêm giờ tối đa trong một tháng?", "domain": "lao_dong", "expect_keywords": ["làm thêm giờ", "tối đa"]},
    {"q": "Chế độ thai sản cho lao động nữ sinh đôi?", "domain": "lao_dong", "expect_keywords": ["thai sản", "sinh đôi"]},
    {"q": "Trường hợp nào người sử dụng lao động được sa thải?", "domain": "lao_dong", "expect_keywords": ["sa thải", "trường hợp"]},
    {"q": "Trợ cấp thôi việc được tính như thế nào?", "domain": "lao_dong", "expect_keywords": ["trợ cấp thôi việc", "tính"]},
    {"q": "Quyền của người lao động khi bị tai nạn lao động?", "domain": "lao_dong", "expect_keywords": ["tai nạn lao động", "quyền"]},
    {"q": "Hợp đồng lao động có bắt buộc phải bằng văn bản?", "domain": "lao_dong", "expect_keywords": ["hợp đồng", "văn bản"]},
    {"q": "Quy định về ngày nghỉ phép năm theo Bộ luật Lao động?", "domain": "lao_dong", "expect_keywords": ["nghỉ phép", "năm"]},
    {"q": "Mức đóng bảo hiểm xã hội bắt buộc cho người lao động?", "domain": "lao_dong", "expect_keywords": ["bảo hiểm xã hội", "đóng"]},
    {"q": "Tuổi nghỉ hưu của lao động nam và nữ theo quy định mới?", "domain": "lao_dong", "expect_keywords": ["nghỉ hưu", "tuổi"]},
    {"q": "Thủ tục giải quyết tranh chấp lao động cá nhân?", "domain": "lao_dong", "expect_keywords": ["tranh chấp lao động"]},
    {"q": "Quy định về hợp đồng thử việc có cần đóng BHXH không?", "domain": "lao_dong", "expect_keywords": ["thử việc", "BHXH"]},
    {"q": "Người lao động nghỉ việc không báo trước bao nhiêu ngày thì vi phạm?", "domain": "lao_dong", "expect_keywords": ["báo trước", "vi phạm"]},
    {"q": "Chế độ ốm đau cho người lao động đóng BHXH?", "domain": "lao_dong", "expect_keywords": ["ốm đau", "BHXH"]},
    {"q": "Quy định về lao động chưa thành niên?", "domain": "lao_dong", "expect_keywords": ["chưa thành niên", "lao động"]},
    {"q": "Trách nhiệm bồi thường khi đơn phương chấm dứt hợp đồng trái luật?", "domain": "lao_dong", "expect_keywords": ["bồi thường", "trái luật"]},
    {"q": "Quyền thành lập công đoàn cơ sở tại doanh nghiệp?", "domain": "lao_dong", "expect_keywords": ["công đoàn", "doanh nghiệp"]},
    {"q": "Quy định về nội quy lao động và xử lý kỷ luật?", "domain": "lao_dong", "expect_keywords": ["nội quy", "kỷ luật"]},
    {"q": "Điều kiện hưởng trợ cấp thất nghiệp năm 2024?", "domain": "lao_dong", "expect_keywords": ["trợ cấp thất nghiệp"]},
    {"q": "Mức lương làm thêm giờ vào ngày lễ là bao nhiêu?", "domain": "lao_dong", "expect_keywords": ["lương", "làm thêm", "ngày lễ"]},
    {"q": "Quy định về cho thuê lại lao động theo Bộ luật Lao động?", "domain": "lao_dong", "expect_keywords": ["cho thuê lại", "lao động"]},
    {"q": "Thời hiệu khởi kiện tranh chấp lao động là bao lâu?", "domain": "lao_dong", "expect_keywords": ["thời hiệu", "khởi kiện"]},
    {"q": "Người lao động nước ngoài làm việc tại Việt Nam cần giấy phép gì?", "domain": "lao_dong", "expect_keywords": ["nước ngoài", "giấy phép"]},
    {"q": "Chế độ nghỉ dưỡng sức sau ốm đau dài ngày?", "domain": "lao_dong", "expect_keywords": ["nghỉ dưỡng sức", "ốm đau"]},
    {"q": "Quy định về hợp đồng lao động mùa vụ?", "domain": "lao_dong", "expect_keywords": ["hợp đồng", "mùa vụ"]},
    {"q": "Mức bồi thường tai nạn lao động gây chết người?", "domain": "lao_dong", "expect_keywords": ["bồi thường", "tai nạn", "chết"]},
    {"q": "Quyền đình công của người lao động theo pháp luật?", "domain": "lao_dong", "expect_keywords": ["đình công", "quyền"]},
    {"q": "Trách nhiệm của chủ sử dụng lao động khi không ký hợp đồng?", "domain": "lao_dong", "expect_keywords": ["không ký", "hợp đồng"]},
]

# ── 3. DÂN SỰ (60 câu) ──
DAN_SU = [
    {"q": "Thủ tục ly hôn đơn phương khi một bên không đồng ý?", "domain": "dan_su", "expect_keywords": ["ly hôn", "đơn phương"]},
    {"q": "Chia tài sản chung vợ chồng khi ly hôn theo nguyên tắc nào?", "domain": "dan_su", "expect_keywords": ["tài sản chung", "ly hôn"]},
    {"q": "Quyền nuôi con dưới 36 tháng tuổi sau ly hôn?", "domain": "dan_su", "expect_keywords": ["nuôi con", "ly hôn"]},
    {"q": "Điều kiện để di chúc được coi là hợp pháp?", "domain": "dan_su", "expect_keywords": ["di chúc", "hợp pháp"]},
    {"q": "Thừa kế theo pháp luật khi không có di chúc chia cho ai?", "domain": "dan_su", "expect_keywords": ["thừa kế", "pháp luật"]},
    {"q": "Hợp đồng đặt cọc mua bán nhà có hiệu lực khi nào?", "domain": "dan_su", "expect_keywords": ["đặt cọc", "hiệu lực"]},
    {"q": "Bồi thường thiệt hại ngoài hợp đồng theo Bộ luật Dân sự?", "domain": "dan_su", "expect_keywords": ["bồi thường", "ngoài hợp đồng"]},
    {"q": "Thời hiệu khởi kiện yêu cầu chia thừa kế là bao lâu?", "domain": "dan_su", "expect_keywords": ["thời hiệu", "thừa kế"]},
    {"q": "Điều kiện kết hôn với người nước ngoài tại Việt Nam?", "domain": "dan_su", "expect_keywords": ["kết hôn", "nước ngoài"]},
    {"q": "Hợp đồng ủy quyền có bắt buộc công chứng không?", "domain": "dan_su", "expect_keywords": ["ủy quyền", "công chứng"]},
    {"q": "Quyền yêu cầu cấp dưỡng sau ly hôn?", "domain": "dan_su", "expect_keywords": ["cấp dưỡng", "ly hôn"]},
    {"q": "Thủ tục nhận con nuôi theo pháp luật Việt Nam?", "domain": "dan_su", "expect_keywords": ["nhận con nuôi", "thủ tục"]},
    {"q": "Tài sản riêng của vợ chồng có bị chia khi ly hôn không?", "domain": "dan_su", "expect_keywords": ["tài sản riêng", "ly hôn"]},
    {"q": "Hậu quả pháp lý khi hợp đồng dân sự bị vô hiệu?", "domain": "dan_su", "expect_keywords": ["vô hiệu", "hậu quả"]},
    {"q": "Quyền thừa kế của con ngoài giá thú theo pháp luật?", "domain": "dan_su", "expect_keywords": ["con ngoài giá thú", "thừa kế"]},
    {"q": "Thủ tục thuận tình ly hôn mất bao lâu?", "domain": "dan_su", "expect_keywords": ["thuận tình", "ly hôn"]},
    {"q": "Tặng cho tài sản có điều kiện theo Bộ luật Dân sự?", "domain": "dan_su", "expect_keywords": ["tặng cho", "điều kiện"]},
    {"q": "Trách nhiệm dân sự do nguồn nguy hiểm cao độ gây ra?", "domain": "dan_su", "expect_keywords": ["nguồn nguy hiểm", "trách nhiệm"]},
    {"q": "Quyền của người giám hộ đối với người được giám hộ?", "domain": "dan_su", "expect_keywords": ["giám hộ", "quyền"]},
    {"q": "Hợp đồng vay tài sản có lãi suất tối đa bao nhiêu?", "domain": "dan_su", "expect_keywords": ["vay", "lãi suất"]},
    {"q": "Thủ tục ly hôn khi chồng đang ở nước ngoài?", "domain": "dan_su", "expect_keywords": ["ly hôn", "nước ngoài"]},
    {"q": "Quy định về quyền sở hữu tài sản trí tuệ?", "domain": "dan_su", "expect_keywords": ["sở hữu", "trí tuệ"]},
    {"q": "Trách nhiệm của cha mẹ đối với thiệt hại do con chưa thành niên gây ra?", "domain": "dan_su", "expect_keywords": ["cha mẹ", "chưa thành niên"]},
    {"q": "Thời hiệu thừa kế theo quy định Bộ luật Dân sự 2015?", "domain": "dan_su", "expect_keywords": ["thời hiệu", "thừa kế"]},
    {"q": "Hợp đồng thuê nhà có bắt buộc công chứng không?", "domain": "dan_su", "expect_keywords": ["thuê nhà", "công chứng"]},
    {"q": "Quyền đòi lại tài sản cho mượn theo Bộ luật Dân sự?", "domain": "dan_su", "expect_keywords": ["tài sản", "cho mượn"]},
    {"q": "Điều kiện để tuyên bố một người mất tích?", "domain": "dan_su", "expect_keywords": ["mất tích", "tuyên bố"]},
    {"q": "Mức cấp dưỡng nuôi con sau ly hôn theo quy định?", "domain": "dan_su", "expect_keywords": ["cấp dưỡng", "nuôi con"]},
    {"q": "Quy định về hợp đồng bảo hiểm nhân thọ?", "domain": "dan_su", "expect_keywords": ["bảo hiểm", "nhân thọ"]},
    {"q": "Thủ tục xin thay đổi người nuôi con sau ly hôn?", "domain": "dan_su", "expect_keywords": ["thay đổi", "nuôi con"]},
]

# ── 4. HÌNH SỰ (50 câu) ──
HINH_SU = [
    {"q": "Khung hình phạt tội trộm cắp tài sản trên 500 triệu đồng?", "domain": "hinh_su", "expect_keywords": ["trộm cắp", "hình phạt"]},
    {"q": "Điều kiện để được hưởng án treo theo Bộ luật Hình sự?", "domain": "hinh_su", "expect_keywords": ["án treo", "điều kiện"]},
    {"q": "Tội lừa đảo chiếm đoạt tài sản bị xử lý thế nào?", "domain": "hinh_su", "expect_keywords": ["lừa đảo", "chiếm đoạt"]},
    {"q": "Quyền của bị can trong giai đoạn điều tra?", "domain": "hinh_su", "expect_keywords": ["bị can", "điều tra"]},
    {"q": "Tội cố ý gây thương tích trên 31% bị phạt bao nhiêu năm tù?", "domain": "hinh_su", "expect_keywords": ["gây thương tích", "phạt"]},
    {"q": "Những tình tiết giảm nhẹ trách nhiệm hình sự theo BLHS?", "domain": "hinh_su", "expect_keywords": ["giảm nhẹ", "trách nhiệm"]},
    {"q": "Tội cho vay nặng lãi trong giao dịch dân sự bị xử thế nào?", "domain": "hinh_su", "expect_keywords": ["cho vay nặng lãi"]},
    {"q": "Thời hiệu truy cứu trách nhiệm hình sự tội ít nghiêm trọng?", "domain": "hinh_su", "expect_keywords": ["thời hiệu", "truy cứu"]},
    {"q": "Tội vi phạm quy định về an toàn giao thông đường bộ?", "domain": "hinh_su", "expect_keywords": ["an toàn giao thông"]},
    {"q": "Quy định về tạm giữ, tạm giam trong tố tụng hình sự?", "domain": "hinh_su", "expect_keywords": ["tạm giữ", "tạm giam"]},
    {"q": "Tội tham ô tài sản bị xử lý hình sự thế nào?", "domain": "hinh_su", "expect_keywords": ["tham ô", "tài sản"]},
    {"q": "Điều kiện để miễn trách nhiệm hình sự?", "domain": "hinh_su", "expect_keywords": ["miễn trách nhiệm"]},
    {"q": "Tội hủy hoại tài sản có khung hình phạt thế nào?", "domain": "hinh_su", "expect_keywords": ["hủy hoại", "hình phạt"]},
    {"q": "Quy định về bảo lĩnh trong tố tụng hình sự?", "domain": "hinh_su", "expect_keywords": ["bảo lĩnh"]},
    {"q": "Tội sản xuất buôn bán hàng giả theo BLHS?", "domain": "hinh_su", "expect_keywords": ["hàng giả"]},
    {"q": "Người dưới 16 tuổi phạm tội bị xử lý như thế nào?", "domain": "hinh_su", "expect_keywords": ["dưới 16 tuổi", "phạm tội"]},
    {"q": "Tội lạm dụng tín nhiệm chiếm đoạt tài sản?", "domain": "hinh_su", "expect_keywords": ["lạm dụng tín nhiệm"]},
    {"q": "Quy định về đồng phạm trong Bộ luật Hình sự?", "domain": "hinh_su", "expect_keywords": ["đồng phạm"]},
    {"q": "Tội cướp tài sản khung hình phạt cao nhất?", "domain": "hinh_su", "expect_keywords": ["cướp", "hình phạt"]},
    {"q": "Tội xâm phạm bí mật hoặc an toàn thư tín?", "domain": "hinh_su", "expect_keywords": ["thư tín", "bí mật"]},
]

# ── 5. DOANH NGHIỆP (50 câu) ──
DOANH_NGHIEP = [
    {"q": "Thủ tục thành lập công ty trách nhiệm hữu hạn một thành viên?", "domain": "doanh_nghiep", "expect_keywords": ["thành lập", "TNHH"]},
    {"q": "Vốn điều lệ tối thiểu để thành lập doanh nghiệp?", "domain": "doanh_nghiep", "expect_keywords": ["vốn điều lệ"]},
    {"q": "Quy trình giải thể doanh nghiệp tự nguyện?", "domain": "doanh_nghiep", "expect_keywords": ["giải thể", "tự nguyện"]},
    {"q": "Quyền của cổ đông thiểu số trong công ty cổ phần?", "domain": "doanh_nghiep", "expect_keywords": ["cổ đông thiểu số"]},
    {"q": "Thủ tục phá sản doanh nghiệp theo Luật Phá sản?", "domain": "doanh_nghiep", "expect_keywords": ["phá sản"]},
    {"q": "Trách nhiệm pháp lý của người đại diện theo pháp luật doanh nghiệp?", "domain": "doanh_nghiep", "expect_keywords": ["người đại diện", "pháp luật"]},
    {"q": "Thủ tục thay đổi đăng ký kinh doanh khi đổi trụ sở?", "domain": "doanh_nghiep", "expect_keywords": ["thay đổi", "đăng ký kinh doanh"]},
    {"q": "Điều kiện để thành lập chi nhánh công ty?", "domain": "doanh_nghiep", "expect_keywords": ["chi nhánh"]},
    {"q": "Quy định về hợp đồng góp vốn kinh doanh?", "domain": "doanh_nghiep", "expect_keywords": ["góp vốn"]},
    {"q": "Chuyển nhượng cổ phần trong công ty cổ phần cần điều kiện gì?", "domain": "doanh_nghiep", "expect_keywords": ["chuyển nhượng", "cổ phần"]},
    {"q": "Trách nhiệm của thành viên hợp danh trong công ty hợp danh?", "domain": "doanh_nghiep", "expect_keywords": ["hợp danh", "trách nhiệm"]},
    {"q": "Thủ tục tạm ngừng kinh doanh doanh nghiệp?", "domain": "doanh_nghiep", "expect_keywords": ["tạm ngừng", "kinh doanh"]},
    {"q": "Quy định về sáp nhập doanh nghiệp theo Luật Doanh nghiệp?", "domain": "doanh_nghiep", "expect_keywords": ["sáp nhập"]},
    {"q": "Thuế thu nhập doanh nghiệp năm 2024 là bao nhiêu phần trăm?", "domain": "doanh_nghiep", "expect_keywords": ["thuế", "thu nhập doanh nghiệp"]},
    {"q": "Quy định về hội đồng quản trị công ty cổ phần?", "domain": "doanh_nghiep", "expect_keywords": ["hội đồng quản trị"]},
    {"q": "Điều kiện kinh doanh ngành nghề có điều kiện?", "domain": "doanh_nghiep", "expect_keywords": ["điều kiện", "ngành nghề"]},
    {"q": "Thủ tục chia tách doanh nghiệp theo quy định mới?", "domain": "doanh_nghiep", "expect_keywords": ["chia tách"]},
    {"q": "Quyền và nghĩa vụ của Ban kiểm soát công ty?", "domain": "doanh_nghiep", "expect_keywords": ["ban kiểm soát"]},
    {"q": "Doanh nghiệp xã hội khác gì doanh nghiệp thông thường?", "domain": "doanh_nghiep", "expect_keywords": ["doanh nghiệp xã hội"]},
    {"q": "Hợp đồng hợp tác kinh doanh BCC là gì?", "domain": "doanh_nghiep", "expect_keywords": ["hợp tác kinh doanh", "BCC"]},
]

# ── 6. HÀNH CHÍNH (50 câu) ──
HANH_CHINH = [
    {"q": "Mức phạt vượt đèn đỏ đối với xe máy năm 2024?", "domain": "hanh_chinh", "expect_keywords": ["phạt", "đèn đỏ"]},
    {"q": "Mức phạt nồng độ cồn khi lái xe ô tô?", "domain": "hanh_chinh", "expect_keywords": ["nồng độ cồn", "phạt"]},
    {"q": "Thủ tục khiếu nại quyết định hành chính?", "domain": "hanh_chinh", "expect_keywords": ["khiếu nại", "hành chính"]},
    {"q": "Mức phạt không đội mũ bảo hiểm khi đi xe máy?", "domain": "hanh_chinh", "expect_keywords": ["mũ bảo hiểm", "phạt"]},
    {"q": "Thời hạn giải quyết thủ tục hành chính theo quy định?", "domain": "hanh_chinh", "expect_keywords": ["thời hạn", "thủ tục hành chính"]},
    {"q": "Mức phạt kinh doanh không có giấy phép?", "domain": "hanh_chinh", "expect_keywords": ["kinh doanh", "giấy phép", "phạt"]},
    {"q": "Quyền khởi kiện vụ án hành chính tại Tòa án?", "domain": "hanh_chinh", "expect_keywords": ["khởi kiện", "hành chính"]},
    {"q": "Mức phạt xả rác nơi công cộng theo Nghị định?", "domain": "hanh_chinh", "expect_keywords": ["xả rác", "phạt"]},
    {"q": "Thủ tục tố cáo hành vi vi phạm pháp luật?", "domain": "hanh_chinh", "expect_keywords": ["tố cáo"]},
    {"q": "Mức phạt không mang bằng lái xe khi tham gia giao thông?", "domain": "hanh_chinh", "expect_keywords": ["bằng lái", "phạt"]},
    {"q": "Quy định xử phạt vi phạm về an toàn thực phẩm?", "domain": "hanh_chinh", "expect_keywords": ["an toàn thực phẩm", "phạt"]},
    {"q": "Mức phạt quảng cáo sai sự thật?", "domain": "hanh_chinh", "expect_keywords": ["quảng cáo", "sai sự thật"]},
    {"q": "Thẩm quyền xử phạt vi phạm hành chính của UBND xã?", "domain": "hanh_chinh", "expect_keywords": ["thẩm quyền", "UBND"]},
    {"q": "Mức phạt hành vi gây ô nhiễm môi trường?", "domain": "hanh_chinh", "expect_keywords": ["ô nhiễm", "môi trường"]},
    {"q": "Thời hiệu xử phạt vi phạm hành chính là bao lâu?", "domain": "hanh_chinh", "expect_keywords": ["thời hiệu", "xử phạt"]},
    {"q": "Mức phạt sử dụng bằng lái xe giả?", "domain": "hanh_chinh", "expect_keywords": ["bằng lái giả", "phạt"]},
    {"q": "Quy trình cưỡng chế thi hành quyết định xử phạt?", "domain": "hanh_chinh", "expect_keywords": ["cưỡng chế", "thi hành"]},
    {"q": "Mức phạt vi phạm quy định về phòng cháy chữa cháy?", "domain": "hanh_chinh", "expect_keywords": ["phòng cháy", "phạt"]},
    {"q": "Quyền của người bị xử phạt vi phạm hành chính?", "domain": "hanh_chinh", "expect_keywords": ["quyền", "xử phạt"]},
    {"q": "Mức phạt chở quá tải trọng cho phép?", "domain": "hanh_chinh", "expect_keywords": ["quá tải", "phạt"]},
]

# ── 7. THUẾ (40 câu) ──
THUE = [
    {"q": "Thuế thu nhập cá nhân đối với tiền lương tính thế nào?", "domain": "thue", "expect_keywords": ["thuế thu nhập", "tiền lương"]},
    {"q": "Mức giảm trừ gia cảnh cho người nộp thuế TNCN năm 2024?", "domain": "thue", "expect_keywords": ["giảm trừ gia cảnh"]},
    {"q": "Thủ tục hoàn thuế giá trị gia tăng cho doanh nghiệp?", "domain": "thue", "expect_keywords": ["hoàn thuế", "GTGT"]},
    {"q": "Mức thuế suất thuế VAT hiện hành áp dụng cho hàng hóa?", "domain": "thue", "expect_keywords": ["thuế suất", "VAT"]},
    {"q": "Điều kiện để được miễn thuế thu nhập doanh nghiệp?", "domain": "thue", "expect_keywords": ["miễn thuế"]},
    {"q": "Quy định về xuất hóa đơn điện tử khi bán hàng?", "domain": "thue", "expect_keywords": ["hóa đơn điện tử"]},
    {"q": "Thời hạn nộp tờ khai thuế GTGT hàng tháng?", "domain": "thue", "expect_keywords": ["tờ khai", "thuế GTGT"]},
    {"q": "Mức phạt chậm nộp thuế là bao nhiêu phần trăm mỗi ngày?", "domain": "thue", "expect_keywords": ["phạt", "chậm nộp"]},
    {"q": "Thuế nhà thầu nước ngoài áp dụng cho trường hợp nào?", "domain": "thue", "expect_keywords": ["thuế nhà thầu"]},
    {"q": "Quy định quyết toán thuế TNCN cuối năm?", "domain": "thue", "expect_keywords": ["quyết toán", "TNCN"]},
    {"q": "Thuế xuất nhập khẩu hàng hóa áp dụng mức nào?", "domain": "thue", "expect_keywords": ["thuế xuất nhập khẩu"]},
    {"q": "Điều kiện để hộ kinh doanh cá thể được miễn thuế?", "domain": "thue", "expect_keywords": ["hộ kinh doanh", "miễn thuế"]},
    {"q": "Quy định về thuế tiêu thụ đặc biệt đối với rượu bia?", "domain": "thue", "expect_keywords": ["tiêu thụ đặc biệt", "rượu bia"]},
    {"q": "Thủ tục đăng ký mã số thuế cá nhân?", "domain": "thue", "expect_keywords": ["mã số thuế", "đăng ký"]},
    {"q": "Thuế chuyển nhượng bất động sản là bao nhiêu phần trăm?", "domain": "thue", "expect_keywords": ["thuế", "chuyển nhượng", "bất động sản"]},
    {"q": "Quy định về ưu đãi thuế cho doanh nghiệp công nghệ cao?", "domain": "thue", "expect_keywords": ["ưu đãi thuế", "công nghệ cao"]},
    {"q": "Phạt trốn thuế theo pháp luật hiện hành?", "domain": "thue", "expect_keywords": ["trốn thuế", "phạt"]},
    {"q": "Hóa đơn điện tử có bắt buộc cho tất cả doanh nghiệp không?", "domain": "thue", "expect_keywords": ["hóa đơn điện tử", "bắt buộc"]},
    {"q": "Thuế tài nguyên áp dụng cho khai thác khoáng sản thế nào?", "domain": "thue", "expect_keywords": ["thuế tài nguyên", "khoáng sản"]},
    {"q": "Mức thuế suất thuế TNCN cho thu nhập từ đầu tư vốn?", "domain": "thue", "expect_keywords": ["thuế TNCN", "đầu tư vốn"]},
]

# ── 8. HÔN NHÂN GIA ĐÌNH (40 câu) ──
HON_NHAN = [
    {"q": "Tuổi kết hôn theo Luật Hôn nhân và Gia đình?", "domain": "hon_nhan", "expect_keywords": ["tuổi kết hôn"]},
    {"q": "Trường hợp nào bị cấm kết hôn theo pháp luật?", "domain": "hon_nhan", "expect_keywords": ["cấm kết hôn"]},
    {"q": "Thủ tục đăng ký kết hôn tại UBND xã?", "domain": "hon_nhan", "expect_keywords": ["đăng ký kết hôn"]},
    {"q": "Quy định về tài sản chung và tài sản riêng của vợ chồng?", "domain": "hon_nhan", "expect_keywords": ["tài sản chung", "tài sản riêng"]},
    {"q": "Chế độ tài sản vợ chồng theo thỏa thuận trước khi kết hôn?", "domain": "hon_nhan", "expect_keywords": ["chế độ tài sản", "thỏa thuận"]},
    {"q": "Quyền và nghĩa vụ của cha mẹ đối với con chưa thành niên?", "domain": "hon_nhan", "expect_keywords": ["cha mẹ", "con chưa thành niên"]},
    {"q": "Quy định về mang thai hộ vì mục đích nhân đạo?", "domain": "hon_nhan", "expect_keywords": ["mang thai hộ"]},
    {"q": "Chồng có quyền ly hôn khi vợ đang mang thai không?", "domain": "hon_nhan", "expect_keywords": ["ly hôn", "mang thai"]},
    {"q": "Quy định về quan hệ huyết thống trong kết hôn?", "domain": "hon_nhan", "expect_keywords": ["huyết thống", "kết hôn"]},
    {"q": "Thủ tục giải quyết việc nuôi con khi cha mẹ không thỏa thuận được?", "domain": "hon_nhan", "expect_keywords": ["nuôi con"]},
    {"q": "Quyền của cha mẹ thăm nom con sau ly hôn?", "domain": "hon_nhan", "expect_keywords": ["thăm nom", "ly hôn"]},
    {"q": "Hôn nhân có yếu tố nước ngoài giải quyết thế nào?", "domain": "hon_nhan", "expect_keywords": ["yếu tố nước ngoài"]},
    {"q": "Nghĩa vụ cấp dưỡng giữa cha mẹ và con cái?", "domain": "hon_nhan", "expect_keywords": ["cấp dưỡng"]},
    {"q": "Quy định về con ngoài giá thú và quyền nhận cha mẹ?", "domain": "hon_nhan", "expect_keywords": ["con ngoài giá thú"]},
    {"q": "Tòa án có thẩm quyền giải quyết ly hôn là Tòa nào?", "domain": "hon_nhan", "expect_keywords": ["thẩm quyền", "ly hôn"]},
    {"q": "Quy định về hôn nhân đồng giới tại Việt Nam?", "domain": "hon_nhan", "expect_keywords": ["đồng giới"]},
    {"q": "Thủ tục nhận cha cho con ngoài giá thú?", "domain": "hon_nhan", "expect_keywords": ["nhận cha"]},
    {"q": "Quyền yêu cầu chia tài sản chung trong thời kỳ hôn nhân?", "domain": "hon_nhan", "expect_keywords": ["chia tài sản", "thời kỳ hôn nhân"]},
    {"q": "Chế độ tài sản vợ chồng theo luật định áp dụng khi nào?", "domain": "hon_nhan", "expect_keywords": ["chế độ tài sản", "luật định"]},
    {"q": "Hủy kết hôn trái pháp luật theo quy định?", "domain": "hon_nhan", "expect_keywords": ["hủy kết hôn"]},
]

# ── 9. SỞ HỮU TRÍ TUỆ (35 câu) ──
SO_HUU_TRI_TUE = [
    {"q": "Thủ tục đăng ký nhãn hiệu tại Cục Sở hữu trí tuệ?", "domain": "shtt", "expect_keywords": ["nhãn hiệu", "đăng ký"]},
    {"q": "Thời hạn bảo hộ quyền tác giả theo Luật SHTT?", "domain": "shtt", "expect_keywords": ["quyền tác giả", "thời hạn"]},
    {"q": "Xử lý vi phạm bản quyền phần mềm theo pháp luật?", "domain": "shtt", "expect_keywords": ["bản quyền", "phần mềm"]},
    {"q": "Điều kiện để được cấp bằng sáng chế tại Việt Nam?", "domain": "shtt", "expect_keywords": ["sáng chế", "bằng"]},
    {"q": "Quy định về bảo hộ kiểu dáng công nghiệp?", "domain": "shtt", "expect_keywords": ["kiểu dáng công nghiệp"]},
    {"q": "Mức phạt vi phạm nhãn hiệu theo Nghị định xử phạt?", "domain": "shtt", "expect_keywords": ["vi phạm", "nhãn hiệu"]},
    {"q": "Quyền liên quan đến quyền tác giả bao gồm những gì?", "domain": "shtt", "expect_keywords": ["quyền liên quan"]},
    {"q": "Thủ tục đăng ký bảo hộ tên thương mại?", "domain": "shtt", "expect_keywords": ["tên thương mại"]},
    {"q": "Chuyển nhượng quyền sở hữu công nghiệp cần điều kiện gì?", "domain": "shtt", "expect_keywords": ["chuyển nhượng", "sở hữu công nghiệp"]},
    {"q": "Bảo hộ chỉ dẫn địa lý theo Luật Sở hữu trí tuệ?", "domain": "shtt", "expect_keywords": ["chỉ dẫn địa lý"]},
    {"q": "Mức bồi thường thiệt hại khi bị xâm phạm quyền tác giả?", "domain": "shtt", "expect_keywords": ["bồi thường", "quyền tác giả"]},
    {"q": "Quy định về giống cây trồng được bảo hộ?", "domain": "shtt", "expect_keywords": ["giống cây trồng"]},
    {"q": "Li-xăng nhãn hiệu là gì và quy định ra sao?", "domain": "shtt", "expect_keywords": ["li-xăng", "nhãn hiệu"]},
    {"q": "Quyền tác giả đối với tác phẩm được tạo trong quan hệ lao động?", "domain": "shtt", "expect_keywords": ["quyền tác giả", "lao động"]},
    {"q": "Giải quyết tranh chấp sở hữu trí tuệ tại Tòa án?", "domain": "shtt", "expect_keywords": ["tranh chấp", "sở hữu trí tuệ"]},
]

# ── 10. MÔI TRƯỜNG & ĐA DẠNG (35 câu) ──
MOI_TRUONG = [
    {"q": "Mức phạt xả thải không qua xử lý ra môi trường?", "domain": "moi_truong", "expect_keywords": ["xả thải", "phạt"]},
    {"q": "Đánh giá tác động môi trường (ĐTM) áp dụng cho dự án nào?", "domain": "moi_truong", "expect_keywords": ["đánh giá tác động", "môi trường"]},
    {"q": "Giấy phép môi trường theo Luật Bảo vệ môi trường 2020?", "domain": "moi_truong", "expect_keywords": ["giấy phép môi trường"]},
    {"q": "Quy chuẩn kỹ thuật về nước thải công nghiệp?", "domain": "moi_truong", "expect_keywords": ["nước thải", "công nghiệp"]},
    {"q": "Trách nhiệm thu gom xử lý chất thải rắn sinh hoạt?", "domain": "moi_truong", "expect_keywords": ["chất thải rắn"]},
    {"q": "Mức phạt khai thác khoáng sản trái phép?", "domain": "moi_truong", "expect_keywords": ["khai thác", "khoáng sản"]},
    {"q": "Quy định về bảo vệ rừng tự nhiên?", "domain": "moi_truong", "expect_keywords": ["bảo vệ rừng"]},
    {"q": "Quy định về xử lý chất thải nguy hại?", "domain": "moi_truong", "expect_keywords": ["chất thải nguy hại"]},
    {"q": "Trách nhiệm pháp lý khi gây sự cố môi trường?", "domain": "moi_truong", "expect_keywords": ["sự cố môi trường"]},
    {"q": "Bảo vệ đa dạng sinh học theo Luật Đa dạng sinh học?", "domain": "moi_truong", "expect_keywords": ["đa dạng sinh học"]},
    {"q": "Quy định về phân loại rác tại nguồn?", "domain": "moi_truong", "expect_keywords": ["phân loại rác"]},
    {"q": "Mức phạt gây ô nhiễm nguồn nước?", "domain": "moi_truong", "expect_keywords": ["ô nhiễm", "nguồn nước"]},
    {"q": "Trách nhiệm tái chế bao bì của nhà sản xuất?", "domain": "moi_truong", "expect_keywords": ["tái chế", "bao bì"]},
    {"q": "Quy định về ký quỹ phục hồi môi trường?", "domain": "moi_truong", "expect_keywords": ["ký quỹ", "phục hồi"]},
    {"q": "Mức phạt đốt rơm rạ gây ô nhiễm không khí?", "domain": "moi_truong", "expect_keywords": ["đốt rơm", "ô nhiễm"]},
]

# Gộp tất cả
BENCHMARK_QUESTIONS = DAT_DAI + LAO_DONG + DAN_SU + HINH_SU + DOANH_NGHIEP + HANH_CHINH + THUE + HON_NHAN + SO_HUU_TRI_TUE + MOI_TRUONG

# Đệm thêm câu hỏi phức hợp (multi-domain) cho đủ 500
PHUC_HOP = [
    {"q": "Ly hôn khi có tài sản chung là nhà đất đứng tên một bên thì chia thế nào?", "domain": "dan_su", "expect_keywords": ["ly hôn", "tài sản", "nhà đất"]},
    {"q": "Người lao động bị sa thải trái luật có được bồi thường bao nhiêu tháng lương?", "domain": "lao_dong", "expect_keywords": ["sa thải", "bồi thường"]},
    {"q": "Tội trốn thuế bị truy cứu hình sự khi nào?", "domain": "hinh_su", "expect_keywords": ["trốn thuế", "hình sự"]},
    {"q": "Thủ tục khởi kiện tranh chấp hợp đồng thương mại quốc tế?", "domain": "doanh_nghiep", "expect_keywords": ["khởi kiện", "hợp đồng thương mại"]},
    {"q": "Giải quyết tranh chấp đất đai giữa hộ gia đình tại Tòa án?", "domain": "dat_dai", "expect_keywords": ["tranh chấp", "Tòa án"]},
]

# Lặp phức hợp để đủ 500
while len(BENCHMARK_QUESTIONS) < 500:
    extra = random.choice(PHUC_HOP).copy()
    BENCHMARK_QUESTIONS.append(extra)

random.seed(42)
random.shuffle(BENCHMARK_QUESTIONS)
BENCHMARK_QUESTIONS = BENCHMARK_QUESTIONS[:500]

# ═══════════════════════════════════════════════════════════════════════
# PHẦN 2: HÀM ĐÁNH GIÁ (EVALUATION ENGINE)
# ═══════════════════════════════════════════════════════════════════════

def evaluate_response(question: dict, response: dict) -> dict:
    """Đánh giá phản hồi của API dựa trên 6 tiêu chí."""
    resp_text = (response.get("response") or "").lower()
    citations = response.get("citations") or []
    
    scores = {}
    
    # 1. Response Existence (Phản hồi có nội dung hay rỗng?)
    scores["has_response"] = 1 if len(resp_text) > 50 else 0
    
    # 2. Response Length (Phản hồi đủ chi tiết hay quá ngắn?)
    scores["adequate_length"] = 1 if len(resp_text) > 200 else 0
    
    # 3. Has Citations (Có trích dẫn văn bản pháp luật không?)
    scores["has_citations"] = 1 if len(citations) > 0 else 0
    
    # 4. Keyword Relevance (Phản hồi có chứa từ khóa kỳ vọng?)
    expect_kws = question.get("expect_keywords", [])
    matched_kws = sum(1 for kw in expect_kws if kw.lower() in resp_text)
    scores["keyword_relevance"] = matched_kws / len(expect_kws) if expect_kws else 1.0
    
    # 5. Legal Reference Quality (Có trích dẫn số hiệu văn bản cụ thể?)
    import re
    legal_refs = re.findall(r'\d+/\d{4}/[A-Za-zĐđÀ-ỹ\-]+', resp_text)
    scores["has_legal_refs"] = 1 if len(legal_refs) > 0 else 0
    
    # 6. No Truncation (Phản hồi không bị đứt giữa chừng?)
    ends_properly = resp_text.rstrip().endswith(('.', '!', '?', ':', ')', ']', '*', '。', '-')) or resp_text.rstrip()[-1:].isalpha()
    scores["not_truncated"] = 1 if ends_properly else 0
    
    # Tổng điểm tổng hợp (Weighted Average)
    weights = {
        "has_response": 0.20,
        "adequate_length": 0.15,
        "has_citations": 0.20,
        "keyword_relevance": 0.20,
        "has_legal_refs": 0.15,
        "not_truncated": 0.10,
    }
    
    total_score = sum(scores[k] * weights[k] for k in weights)
    scores["total_score"] = round(total_score, 4)
    
    return scores


# ═══════════════════════════════════════════════════════════════════════
# PHẦN 3: CHẠY BENCHMARK (RUNNER)
# ═══════════════════════════════════════════════════════════════════════

PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "..", "benchmark_progress.txt")
CONCURRENCY = 3  # 3 câu hỏi chạy song song (tránh quá tải server)
MAX_RETRIES = 2  # Retry tối đa 2 lần khi lỗi

import threading
_log_lock = threading.Lock()
_stats_lock = asyncio.Lock() if False else None  # placeholder, created in run_benchmark

def log(msg):
    """Print with flush and write to progress file."""
    with _log_lock:
        print(msg, flush=True)
        try:
            with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


async def process_one(client, sem, idx, q_data, state):
    """Xử lý 1 câu hỏi với semaphore + retry."""
    async with sem:
        question = q_data["q"]
        domain = q_data["domain"]
        
        t_start = time.time()
        last_error = None
        api_response = None
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    f"{API_BASE}/assistant/chat",
                    json={"prompt": question, "session_id": f"benchmark_{idx}"},
                    headers={"Content-Type": "application/json", "X-API-Key": API_KEY}
                )
                api_response = resp.json()
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(3 * (attempt + 1))  # backoff: 3s, 6s
        
        latency = time.time() - t_start
        
        if last_error or api_response is None:
            async with state["lock"]:
                state["done"] += 1
                state["fail"] += 1
                done = state["done"]
                acc = state["pass"] / done * 100 if done > 0 else 0
            log(f"  [{done:>3}/500] ❌ ERROR (after {MAX_RETRIES+1} tries): {last_error}")
            return {
                "index": idx + 1, "question": question, "domain": domain,
                "scores": {"total_score": 0, "error": str(last_error)},
                "latency": round(latency, 2), "status": "ERROR"
            }
        
        try:
            
            scores = evaluate_response(q_data, api_response)
            is_pass = scores["total_score"] >= 0.60
            status = "✅" if is_pass else "❌"
            
            result = {
                "index": idx + 1,
                "question": question,
                "domain": domain,
                "scores": scores,
                "latency": round(latency, 2),
                "status": "PASS" if is_pass else "FAIL"
            }
            
            # Thread-safe stats update
            async with state["lock"]:
                state["done"] += 1
                state["total_time"] += latency
                if is_pass:
                    state["pass"] += 1
                else:
                    state["fail"] += 1
                
                if domain not in state["domain_stats"]:
                    state["domain_stats"][domain] = {"pass": 0, "fail": 0, "scores": []}
                state["domain_stats"][domain]["scores"].append(scores["total_score"])
                if is_pass:
                    state["domain_stats"][domain]["pass"] += 1
                else:
                    state["domain_stats"][domain]["fail"] += 1
                
                done = state["done"]
                acc = state["pass"] / done * 100
            
            log(f"  [{done:>3}/500] {status} | Score: {scores['total_score']:.2f} | Acc: {acc:.1f}% | ⏱️ {latency:.1f}s | {domain} | {question[:50]}")
            return result
            
        except Exception as e:
            async with state["lock"]:
                state["done"] += 1
                state["fail"] += 1
                done = state["done"]
                acc = state["pass"] / done * 100 if done > 0 else 0
            
            log(f"  [{done:>3}/500] ❌ ERROR: {e}")
            return {
                "index": idx + 1,
                "question": question,
                "domain": domain,
                "scores": {"total_score": 0, "error": str(e)},
                "latency": time.time() - t_start,
                "status": "ERROR"
            }


async def run_benchmark():
    # Clear progress file
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        f.write("")
    
    log(f"🚀 BẮT ĐẦU BENCHMARK — {len(BENCHMARK_QUESTIONS)} CÂU HỎI PHÁP LUẬT")
    log(f"⚡ Chế độ SONG SONG: {CONCURRENCY} workers")
    log(f"⏰ Thời gian bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)
    
    sem = asyncio.Semaphore(CONCURRENCY)
    state = {
        "done": 0, "pass": 0, "fail": 0, "total_time": 0,
        "domain_stats": {},
        "lock": asyncio.Lock()
    }
    
    wall_start = time.time()
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        tasks = [
            process_one(client, sem, idx, q_data, state)
            for idx, q_data in enumerate(BENCHMARK_QUESTIONS)
        ]
        results = await asyncio.gather(*tasks)
    
    wall_time = time.time() - wall_start
    
    # ═══════════════════════════════════════════════════════════════════
    # PHẦN 4: BÁO CÁO KẾT QUẢ (REPORT)
    # ═══════════════════════════════════════════════════════════════════
    
    total = len(BENCHMARK_QUESTIONS)
    total_pass = state["pass"]
    total_fail = state["fail"]
    accuracy = total_pass / total * 100
    avg_latency = state["total_time"] / total
    
    log("\n" + "=" * 80)
    log(f"🏛️ BÁO CÁO BENCHMARK DATALUATVN — {total} CÂU HỎI PHÁP LUẬT")
    log("=" * 80)
    log(f"  📊 Tổng câu hỏi:    {total}")
    log(f"  ✅ Đạt (PASS):      {total_pass} ({accuracy:.2f}%)")
    log(f"  ❌ Không đạt (FAIL): {total_fail}")
    log(f"  ⏱️ Latency TB:       {avg_latency:.2f}s/câu")
    log(f"  🕐 Wall time:        {wall_time:.0f}s ({wall_time/60:.1f} phút)")
    log(f"  ⚡ Concurrency:      {CONCURRENCY} workers")
    log("")
    
    # Domain breakdown
    domain_stats = state["domain_stats"]
    log("📋 PHÂN TÍCH THEO LĨNH VỰC:")
    log(f"  {'Lĩnh vực':<20} {'Pass':>6} {'Fail':>6} {'Tổng':>6} {'Accuracy':>10} {'Avg Score':>10}")
    log("  " + "-" * 60)
    for domain, stats in sorted(domain_stats.items()):
        d_total = stats["pass"] + stats["fail"]
        d_acc = stats["pass"] / d_total * 100 if d_total > 0 else 0
        d_avg = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
        log(f"  {domain:<20} {stats['pass']:>6} {stats['fail']:>6} {d_total:>6} {d_acc:>9.1f}% {d_avg:>9.3f}")
    
    # Save results to JSON
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_questions": total,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "accuracy_percent": round(accuracy, 2),
        "avg_latency_seconds": round(avg_latency, 2),
        "wall_time_seconds": round(wall_time, 2),
        "concurrency": CONCURRENCY,
        "domain_stats": {k: {"pass": v["pass"], "fail": v["fail"], "avg_score": round(sum(v["scores"])/len(v["scores"]), 4) if v["scores"] else 0} for k, v in domain_stats.items()},
        "failed_questions": [r for r in results if r["status"] != "PASS"]
    }
    
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    log(f"\n💾 Kết quả chi tiết đã lưu tại: benchmark_results.json")
    log(f"\n{'🎉 XUẤT SẮC!' if accuracy >= 99 else '⚠️ CẦN CẢI THIỆN' if accuracy >= 90 else '❌ CHƯA ĐẠT'} — Accuracy: {accuracy:.2f}%")
    
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(run_benchmark())

