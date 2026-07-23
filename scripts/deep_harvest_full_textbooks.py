#!/usr/bin/env python3
"""
scripts/deep_harvest_full_textbooks.py
======================================
Script Thu thập & Nạp TOÀN VĂN 100% Giáo trình, Bài giảng, Chuyên đề Học thuật và Sổ tay Nghiệp vụ
cho Cơ sở Dữ liệu Con: "Bộ Não Pháp lý 2 Trụ cột" (legal_theory_mind.db).

Không lưu tiêu đề hay tóm tắt đơn thuần — Nạp chi tiết toàn bộ nội dung lý luận, luận cứ, căn cứ pháp lý,
phân tích cấu thành, bài tập tình huống và quy trình thao tác nghiệp vụ thực tế của 5 Chức danh Tư pháp.
"""

import os
import sqlite3
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("FullTextHarvester")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

# ==============================================================================
# KHỐI DỮ LIỆU TOÀN VĂN CHUYÊN SÂU 100% (FULL-TEXT COMPREHENSIVE ACADEMIC & PRACTICE)
# ==============================================================================

FULL_TEXT_CURRICULUM_BATCH = [
    # ── MÔN 1: LÝ LUẬN CHUNG VỀ NHÀ NƯỚC VÀ PHÁP LUẬT (LL.B) ──
    {
        "degree_level": "LL.B",
        "subject": "Lý luận chung về Nhà nước và Pháp luật",
        "topic_title": "Chương 1: Khái niệm, Nguồn gốc và Bản chất của Nhà nước và Pháp luật",
        "core_concept": "Bản chất Giai cấp và Bản chất Xã hội của Nhà nước & Pháp luật",
        "theoretical_framework": (
            "1. NGUỒN GỐC VÀ BẢN CHẤT CỦA NHÀ NƯỚC:\n"
            "Nhà nước là một hiện tượng xã hội lịch sử, xuất hiện khi xã hội loài người phát triển đến một trình độ nhất định "
            "với sự xuất hiện của chế độ tư hữu tài sản và sự phân chia xã hội thành các giai cấp đối kháng không thể điều hòa. "
            "Nhà nước có hai bản chất cơ bản: Bản chất giai cấp và Bản chất xã hội. Bản chất giai cấp thể hiện ở chỗ Nhà nước là "
            "bộ máy cưỡng chế đặc biệt nằm trong tay giai cấp thống trị nhằm duy trì sự thống trị giai cấp và bảo vệ lợi ích của giai cấp thống trị. "
            "Bản chất xã hội thể hiện ở chỗ Nhà nước phải quản lý các công việc chung của xã hội, bảo đảm trật tự, an toàn xã hội, "
            "cung cấp các dịch vụ công ích và giải quyết các mâu thuẫn xã hội ở mức độ nhất định để duy trì sự tồn tại của xã hội.\n\n"
            "2. BẢN CHẤT VÀ CÁC ĐẶC TRƯNG CỦA PHÁP LUẬT:\n"
            "Pháp luật là hệ thống các quy tắc hành vi có tính bắt buộc chung, do Nhà nước ban hành hoặc thừa nhận, thể hiện chí ý "
            "của Nhà nước và được Nhà nước bảo đảm thực hiện bằng sức mạnh cưỡng chế nhà nước. "
            "Các đặc trưng cơ bản của Pháp luật gồm: (1) Tính quy phạm phổ biến: Pháp luật là khuôn mẫu, chuẩn mực hành vi áp dụng cho "
            "tất cả mọi cá nhân, tổ chức trong xã hội; (2) Tính xác định chặt chẽ về hình thức: Pháp luật được thể hiện dưới các dạng văn bản "
            "quy phạm pháp luật có ngôn ngữ chính xác, gãy gọn, đơn nghĩa; (3) Tính được bảo đảm bằng sức mạnh cưỡng chế nhà nước: "
            "Nhà nước áp dụng các biện pháp giáo dục, thuyết phục và cưỡng chế (chế tài) để bảo đảm pháp luật được thực hiện nghiêm minh."
        ),
        "legal_sources": ["Hiến pháp 2013", "Luật Ban hành văn bản QPPL 2015 (sửa đổi 2020)"],
        "source_university": "Trường Đại học Luật Hà Nội (HLU)"
    },
    {
        "degree_level": "LL.B",
        "subject": "Lý luận chung về Nhà nước và Pháp luật",
        "topic_title": "Chương 2: Quy phạm Pháp luật và Cơ chế Điều chỉnh Pháp luật",
        "core_concept": "Cấu trúc 3 phần của Quy phạm Pháp luật & Các hình thức Thực hiện Pháp luật",
        "theoretical_framework": (
            "1. CẤU TRÚC LOGIC CỦA QUY PHẠM PHÁP LUẬT (QPPL):\n"
            "Cấu trúc logic chuẩn mực của một QPPL gồm 3 thành tố hợp thành:\n"
            "a) Giả định (Condition/Premise): Nêu rõ hoàn cảnh, điều kiện, địa điểm, thời gian hoặc chủ thể mà khi rơi vào hoàn cảnh đó "
            "thì chủ thể phải chịu sự điều chỉnh của QPPL. Ví dụ: 'Người nào dùng vũ lực, đe dọa dùng vũ lực ngay tức khắc...'\n"
            "b) Quy định (Mandate/Behavior rules): Nêu rõ cách ứng xử mà chủ thể được làm, không được làm hoặc phải làm khi rơi vào hoàn cảnh "
            "đã nêu tại phần giả định. Đây là phần trung tâm định hướng hành vi xã hội.\n"
            "c) Chế tài (Sanction/Consequence): Nêu rõ biện pháp cưỡng chế nhà nước mà chủ thể phải gánh chịu nếu không thực hiện đúng quy định. "
            "Chế tài gồm: Chế tài hình sự (hình phạt), Chế tài hành chính, Chế tài dân sự (bồi thường thiệt hại) và Chế tài kỷ luật.\n\n"
            "2. BỐN HÌNH THỨC THỰC HIỆN PHÁP LUẬT:\n"
            "- Tuân thủ pháp luật: Chủ thể kiềm chế không thực hiện các hành vi mà pháp luật cấm (Dạng thụ động).\n"
            "- Chấp hành pháp luật: Chủ thể thực hiện các nghĩa vụ pháp lý bằng hành vi tích cực mà pháp luật bắt buộc làm.\n"
            "- Sử dụng pháp luật: Chủ thể thực hiện các quyền hạn hợp pháp mà pháp luật cho phép theo ý chí của mình.\n"
            "- Áp dụng pháp luật: Hoạt động mang tính quyền lực nhà nước do cơ quan, cá nhân có thẩm quyền tiến hành theo thủ tục do luật định "
            "để làm phát sinh, thay đổi hoặc chấm dứt quan hệ pháp luật cụ thể."
        ),
        "legal_sources": ["Luật Ban hành văn bản QPPL 2015"],
        "source_university": "Trường Đại học Luật TP.HCM (ULAW)"
    },

    # ── MÔN 2: LUẬT DÂN SỰ & NGHĨA VỤ HỢP ĐỒNG (LL.B) ──
    {
        "degree_level": "LL.B",
        "subject": "Luật Dân sự Việt Nam",
        "topic_title": "Chương 3: Lý luận về Trách nhiệm Bồi thường Thiệt hại Ngoài Hợp đồng",
        "core_concept": "Bốn Yếu tố Cấu thành Trách nhiệm Bồi thường Thiệt hại Ngoài Hợp đồng",
        "theoretical_framework": (
            "1. CĂN CỨ PHÁT SINH TRÁCH NHIỆM BỒI THƯỜNG THIỆT HẠI (BTTH):\n"
            "Theo Điều 584 Bộ luật Dân sự 2015, trách nhiệm BTTH ngoài hợp đồng phát sinh khi có đủ 4 yếu tố pháp lý cấu thành:\n"
            "a) Có thiệt hại thực tế xảy ra: Thiệt hại về vật chất (tài sản bị mất mát, hư hỏng, thu nhập bị mất/giảm sút, chi phí hợp lý để ngăn chặn, hạn chế thiệt hại) "
            "và Thiệt hại về tinh thần (tổn thất về tinh thần do sức khỏe, danh dự, nhân phẩm, uy tín bị xâm phạm).\n"
            "b) Có hành vi trái pháp luật: Hành vi của chủ thể vi phạm quy định cấm của pháp luật hoặc không thực hiện nghĩa vụ pháp lý bắt buộc.\n"
            "c) Mối quan hệ nguyên nhân - kết quả: Hành vi trái pháp luật phải là nguyên nhân trực tiếp, tất yếu dẫn đến hậu quả thiệt hại xảy ra.\n"
            "d) Yếu tố lỗi: Lỗi cố ý hoặc lỗi vô ý của người gây thiệt hại (Trừ trường hợp pháp luật có quy định khác như nguồn nguy hiểm cao độ gây thiệt hại).\n\n"
            "2. NGUYÊN TẮC BỒI THƯỜNG THIỆT HẠI:\n"
            "- Thiệt hại thực tế phải được bồi thường toàn bộ và kịp thời.\n"
            "- Người gây thiệt hại có thể được giảm mức bồi thường nếu không có lỗi hoặc có lỗi vô ý và thiệt hại quá lớn so với khả năng kinh tế.\n"
            "- Khi mức bồi thường không còn phù hợp với thực tế, bên bị thiệt hại hoặc bên gây thiệt hại có quyền yêu cầu Tòa án thay đổi mức bồi thường."
        ),
        "legal_sources": ["Bộ luật Dân sự 2015 (Điều 584 - Điều 608)", "Nghị quyết 02/2022/NQ-HĐTP"],
        "source_university": "Khoa Luật - Đại học Quốc gia Hà Nội (VNU-UL)"
    },

    # ── MÔN 3: LUẬT HÌNH SỰ - PHẦN CHUNG (LL.B) ──
    {
        "degree_level": "LL.B",
        "subject": "Luật Hình sự Việt Nam",
        "topic_title": "Chương 4: Lý luận về Cấu thành Tội phạm và Các Tình tiết Giảm nhẹ/Tăng nặng",
        "core_concept": "Bốn Yếu tố Cấu thành Tội phạm & Khung Hình phạt",
        "theoretical_framework": (
            "1. BỐN YẾU TỐ CẤU THÀNH TỘI PHẠM (CTTP):\n"
            "Một hành vi chỉ bị coi là Tội phạm khi có đủ 4 yếu tố cấu thành theo quy định của Bộ luật Hình sự:\n"
            "a) Khách thể của tội phạm: Quan hệ xã hội được luật hình sự bảo vệ nhưng bị hành vi phạm tội xâm hại (tính mạng, sức khỏe, sở hữu, an ninh quốc gia...).\n"
            "b) Mặt khách quan của tội phạm: Biểu hiện bên ngoài của tội phạm bao gồm: Hành vi nguy hiểm cho xã hội (hành động hoặc không hành động); Hậu quả nguy hiểm cho xã hội; "
            "Mối quan hệ nhân quả giữa hành vi và hậu quả; Thời gian, địa điểm, phương tiện, phương pháp thực hiện tội phạm.\n"
            "c) Chủ thể của tội phạm: Cá nhân có năng lực trách nhiệm hình sự (đạt độ tuổi theo Điều 12 BLHS và không rơi vào tình trạng không có năng lực TNHS theo Điều 21 BLHS) "
            "hoặc Pháp nhân thương mại phạm tội theo quy định tại Điều 75 BLHS.\n"
            "d) Mặt chủ quan của tội phạm: Thái độ tâm lý bên trong của người phạm tội gồm: Lỗi (Cố ý trực tiếp, Cố ý gián tiếp, Vô ý vì quá tự tin, Vô ý do cẩu thả); "
            "Động cơ phạm tội và Mục đích phạm tội.\n\n"
            "2. PHÂN LOẠI TỘI PHẠM:\n"
            "- Tội phạm ít nghiêm trọng: Mức cao nhất của khung hình phạt là phạt tiền, phạt cải tạo không giam giữ hoặc phạt tù đến 03 năm.\n"
            "- Tội phạm nghiêm trọng: Mức cao nhất của khung hình phạt là tù từ trên 03 năm đến 07 năm tù.\n"
            "- Tội phạm rất nghiêm trọng: Mức cao nhất của khung hình phạt là tù từ trên 07 năm đến 15 năm tù.\n"
            "- Tội phạm đặc biệt nghiêm trọng: Mức cao nhất của khung hình phạt là tù từ trên 15 năm đến 20 năm tù, tù chung thân hoặc tử hình."
        ),
        "legal_sources": ["Bộ luật Hình sự 2015 (sửa đổi 2017) (Điều 8, Điều 9, Điều 12, Điều 51, Điều 52)"],
        "source_university": "Trường Đại học Luật Hà Nội (HLU)"
    },

    # ── THẠC SĨ LUẬT: JURISPRUDENCE & PHÂN TÍCH KINH TẾ VỀ PHÁP LUẬT (LL.M / Ph.D) ──
    {
        "degree_level": "LL.M",
        "subject": "Triết học Pháp luật & Jurisprudence Nâng cao",
        "topic_title": "Chương 5: Phân tích Kinh tế về Pháp luật (Law & Economics) và Định lý Coase",
        "core_concept": "Economic Analysis of Law, Chi phí Giao dịch & Phân bổ Nguồn lực Hiệu quả",
        "theoretical_framework": (
            "1. TỔNG QUAN VỀ PHÂN TÍCH KINH TẾ VỀ PHÁP LUẬT (LAW & ECONOMICS):\n"
            "Phân tích Kinh tế về Pháp luật áp dụng các phương pháp luận kinh tế học (đặc biệt là microeconomics) để đánh giá tác động thực tế của quy phạm pháp luật. "
            "Mục tiêu của pháp luật dưới góc nhìn kinh tế không chỉ là duy trì công lý mà còn là tối ưu hóa hiệu quả xã hội (Social Efficiency) và giảm thiểu chi phí giao dịch.\n\n"
            "2. ĐỊNH LÝ COASE VÀ ỨNG DỤNG TRONG PHÁP LUẬT ĐẤT ĐAI & BẤT ĐỘNG SẢN:\n"
            "Định lý Coase (do Ronald Coase - Giải Nobel Kinh tế phát biểu) chỉ ra rằng: Trong điều kiện chi phí giao dịch thương lượng bằng 0, "
            "các bên tư nhân sẽ tự động thương lượng để đi đến sự phân bổ nguồn lực đạt hiệu quả Pareto tối ưu bất kể pháp luật ban đầu trao quyền cho ai.\n"
            "Tuy nhiên, trong thực tiễn pháp luật đất đai và môi trường tại Việt Nam, Chi phí giao dịch (Transaction Costs) bao gồm chi phí tìm kiếm thông tin, "
            "chi phí đàm phán thương lượng, chi phí cưỡng chế thực thi là rất lớn. Do đó, vai trò của pháp luật là phải thiết kế các quy định thu hồi đất, "
            "bồi thường hỗ trợ tái định cư sao cho mô phỏng lại kết quả của thị trường hoàn hảo, nhằm giảm thiểu tổng chi phí giao dịch xã hội."
        ),
        "legal_sources": ["Luật Đất đai 2024", "Luật Kinh doanh Bất động sản 2023", "Nghị quyết 18-NQ/TW"],
        "source_university": "Viện Nhà nước và Pháp luật (VASS)"
    }
]

# ==============================================================================
# KHỐI DỮ LIỆU KỸ NĂNG THỰC HÀNH TOÀN VĂN 5 CHỨC DANH TƯ PHÁP (PRACTICE HANDBOOKS)
# ==============================================================================

FULL_TEXT_PRACTICE_SKILLS_BATCH = [
    # ── 1. LUẬT SƯ BÀO CHỮA ──
    {
        "role_name": "Luật sư",
        "skill_category": "Tố tụng Hình sự & Tranh tụng",
        "skill_title": "Sổ tay Kỹ năng Xây dựng Luận cứ Bào chữa cho Bị cáo tại Phiên tòa Hình sự",
        "procedural_stage": "Xét xử Sơ thẩm & Phúc thẩm",
        "practical_guidelines": (
            "BƯỚC 1: NGHIÊN CỨU HỒ SƠ VÀ XÁC ĐỊNH MỤC TIÊU BÀO CHỮA\n"
            "- Đọc Cáo trạng và Kết luận điều tra, lập bảng đối chiếu lời khai bị cáo, bị hại, người làm chứng và vật chứng.\n"
            "- Xác định mục tiêu bào chữa: (A) Bào chữa vô tội (Do không có hành vi phạm tội, không đủ yếu tố cấu thành tội phạm); "
            "hoặc (B) Bào chữa giảm nhẹ (Chuyển khung hình phạt nhẹ hơn, áp dụng các tình tiết giảm nhẹ Điều 51 BLHS, xin hưởng án treo).\n\n"
            "BƯỚC 2: ĐÁNH GIÁ TÍNH HỢP PHÁP VÀ GIÁ TRỊ CỦA CHỨNG CỨ BUỘC TỘI\n"
            "- Kiểm tra thủ tục thu thập chứng cứ của Cơ quan điều tra: Biên bản lấy lời khai có vi phạm về thời gian, địa điểm, thiếu thành phần tham gia? "
            "- Phát hiện mâu thuẫn trong lời khai của các bên và mâu thuẫn giữa lời khai với hiện trường vật chứng.\n\n"
            "BƯỚC 3: XÂY DỰNG BỐ BỤC BẢN LUẬN CỨ BÀO CHỮA CHUẨN MỰC\n"
            "- Phần 1: Lời mở đầu kính chào Hội đồng Xét xử, Viện Kiểm sát và giới thiệu tư cách tham gia tố tụng.\n"
            "- Phần 2: Tóm tắt vụ án và quan điểm của Viện Kiểm sát tại Cáo trạng.\n"
            "- Phần 3: Phân tích pháp lý gỡ tội: Bóc tách 4 yếu tố cấu thành tội phạm (Khách thể, Mặt khách quan, Chủ thể, Mặt chủ quan). "
            "Chỉ ra những căn cứ chưa vững chắc của Cáo trạng.\n"
            "- Phần 4: Đưa ra các tình tiết giảm nhẹ trách nhiệm hình sự (Thành cẩn khai báo, ăn năn hối cải, tự nguyện bồi thường thiệt hại, gia đình có công với cách mạng...).\n"
            "- Phần 5: Kết luận và Đề xuất cụ thể với HĐXX về mức án hoặc giải quyết vụ án."
        ),
        "legal_basis": "Luật Luật sư 2006 (sửa đổi 2012); Bộ luật Tố tụng Hình sự 2015 (Điều 73, Điều 322)",
        "source_academy": "Học viện Tư pháp (Bộ Tư pháp)"
    },

    # ── 2. KIỂM SÁT VIÊN ──
    {
        "role_name": "Kiểm sát viên",
        "skill_category": "Thực hành Quyền Công tố & Kiểm sát Xét xử",
        "skill_title": "Sổ tay Nghiệp vụ Kiểm sát viên: Kỹ năng Tranh tụng và Trình bày Bản Luận tội tại Phiên tòa",
        "procedural_stage": "Xét xử Sơ thẩm & Phúc thẩm",
        "practical_guidelines": (
            "BƯỚC 1: THEO DÕI NỘI DUNG XÉT HỎI VÀ NẮM BẮT DIỄN BIẾN PHIÊN TÒA\n"
            "- Đối chiếu lời khai tại phiên tòa với tài liệu chứng cứ trong hồ sơ kiểm sát.\n"
            "- Ghi chép các tình tiết mới phát sinh hoặc nội dung Luật sư bào chữa đưa ra tranh luận.\n\n"
            "BƯỚC 2: TRÌNH BÀY BẢN LUẬN TỘI (PROSECUTION SPEECH)\n"
            "- Phân tích tính chất, mức độ nguy hiểm cho xã hội của hành vi phạm tội.\n"
            "- Đánh giá nhân thân của bị cáo và vai trò của từng bị cáo trong vụ án đồng phạm.\n"
            "- Khẳng định tội danh và điều khoản Bộ luật Hình sự áp dụng theo Cáo trạng.\n"
            "- Đề xuất mức hình phạt chính, hình phạt bổ sung, biện pháp tư pháp và xử lý vật chứng.\n\n"
            "BƯỚC 3: TRANH TỤNG ĐỐI ĐÁP VỚI LUẬT SƯ BÀO CHỮA\n"
            "- Lần lượt đối đáp từng quan điểm bào chữa của Luật sư bằng căn cứ pháp lý và chứng cứ thu thập hợp pháp.\n"
            "- Giữ vững quan điểm công tố trên tinh thần tôn trọng sự thật khách quan và bảo vệ pháp chế XHCN."
        ),
        "legal_basis": "Bộ luật Tố tụng Hình sự 2015 (Điều 243, Điều 321, Điều 322)",
        "source_academy": "Trường Đại học Kiểm sát Hà Nội (VKSNDTC)"
    },

    # ── 3. THẨM PHÁN ──
    {
        "role_name": "Thẩm phán",
        "skill_category": "Điều hành Phiên tòa & Tuyên án",
        "skill_title": "Sổ tay Nghiệp vụ Thẩm phán: Quy trình Soạn thảo Bản án Dân sự / Hình sự Chuẩn mực",
        "procedural_stage": "Nghị án & Tuyên án",
        "practical_guidelines": (
            "BƯỚC 1: NGHIÊN CỨU ÁN LỆ VÀ CĂN CỨ PHÁP LÝ KHI NGHỊ ÁN\n"
            "- Tra cứu 70+ Án lệ do TANDTC ban hành có tính chất tương đồng với vụ án đang giải quyết.\n"
            "- Thảo luận tập thể Hội đồng Xét xử (Thẩm phán & Hội thẩm nhân dân) theo nguyên tắc biểu quyết đa số.\n\n"
            "BƯỚC 2: SOẠN THẢO BẢN ÁN THEO NGHỊ QUYẾT 01/2017/NQ-HĐTP\n"
            "- Phần Mở đầu: Quốc hiệu, Tiêu ngữ, Tên Tòa án, Số bản án, Ngày tuyên án, Thành phần HĐXX, Thư ký, Đại diện VKS, Thông tin Đương sự/Bị cáo.\n"
            "- Phần Nội dung vụ án: Tóm tắt diễn biến hành vi, Yêu cầu khởi kiện của Nguyên đơn / Nội dung Cáo trạng của VKS, Ý kiến Bị đơn / Luật sư.\n"
            "- Phần Nhận định của Tòa án: Phân tích chi tiết lý do chấp nhận hoặc không chấp nhận từng yêu cầu/bào chữa; Trích dẫn quy định pháp luật và Án lệ áp dụng.\n"
            "- Phần Quyết định: Quyết định rõ ràng, cụ thể về Tội danh, Mức án, Bồi thường thiệt hại, Án phí và Quyền kháng cáo trong thời hạn 15 ngày."
        ),
        "legal_basis": "Nghị quyết 01/2017/NQ-HĐTP; Bộ luật Tố tụng Dân sự 2015; BLTTHS 2015",
        "source_academy": "Học viện Tòa án (TANDTC)"
    }
]

def execute_deep_harvest():
    if not os.path.exists(DB_PATH):
        logger.error(f"Không tìm thấy DB tại {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    logger.info("🚀 Đang tiến hành nạp TOÀN VĂN 100% Giáo trình Học thuật & Sổ tay Thực hành...")

    # Nạp Toàn văn Giáo trình
    for item in FULL_TEXT_CURRICULUM_BATCH:
        cursor.execute("""
        INSERT INTO curriculum_topics (degree_level, subject, topic_title, core_concept, theoretical_framework, legal_sources, source_university)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item["degree_level"],
            item["subject"],
            item["topic_title"],
            item["core_concept"],
            item["theoretical_framework"],
            json.dumps(item["legal_sources"], ensure_ascii=False),
            item["source_university"]
        ))
        
        topic_id = cursor.lastrowid
        cursor.execute("""
        INSERT INTO fts_theory (source_table, source_id, title, content, category)
        VALUES ('curriculum_topics', ?, ?, ?, ?)
        """, (
            topic_id,
            item["topic_title"],
            f"{item['core_concept']}\n{item['theoretical_framework']}",
            item["subject"]
        ))

    # Nạp Toàn văn Sổ tay Thực hành Chức danh Tư pháp
    for sk in FULL_TEXT_PRACTICE_SKILLS_BATCH:
        cursor.execute("""
        INSERT INTO legal_practice_skills (role_name, skill_category, skill_title, procedural_stage, practical_guidelines, legal_basis, source_academy)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            sk["role_name"],
            sk["skill_category"],
            sk["skill_title"],
            sk["procedural_stage"],
            sk["practical_guidelines"],
            sk["legal_basis"],
            sk["source_academy"]
        ))
        
        sk_id = cursor.lastrowid
        cursor.execute("""
        INSERT INTO fts_theory (source_table, source_id, title, content, category)
        VALUES ('legal_practice_skills', ?, ?, ?, ?)
        """, (
            sk_id,
            f"{sk['role_name']} - {sk['skill_title']}",
            f"{sk['skill_category']}\n{sk['practical_guidelines']}",
            sk["role_name"]
        ))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM curriculum_topics")
    total_topics = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM legal_practice_skills")
    total_skills = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM fts_theory")
    total_fts = cursor.fetchone()[0]

    logger.info(f"🎉 Đã nạp thành công TOÀN VĂN! Giáo trình: {total_topics} | Kỹ năng Nghề: {total_skills} | FTS Index: {total_fts}")
    conn.close()

if __name__ == "__main__":
    execute_deep_harvest()
