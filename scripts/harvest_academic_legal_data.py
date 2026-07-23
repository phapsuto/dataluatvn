#!/usr/bin/env python3
"""
scripts/harvest_academic_legal_data.py
======================================
Script thu thập và tự động làm giàu bộ dữ liệu con "Legal Theory & Academic Brain" (legal_theory_mind.db).
Bao gồm:
1. Nạp ma trận chương trình giáo trình chuẩn LL.B, LL.M, Ph.D từ 4 trường đại học luật lớn.
2. Thu thập tóm tắt luận án tiến sĩ luật và chuyên đề học thuyết pháp lý.
3. Cập nhật chỉ số FTS5 để phục vụ truy xuất RAG Hybrid.
"""

import os
import sqlite3
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("AcademicHarvester")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

# Ma trận Tri thức Chuyên sâu Chi tiết (Comprehensive Academic Curriculum Matrix Data)
ACADEMIC_DATA_BATCH = [
    # --- LL.B: CỬ NHÂN LUẬT ---
    {
        "degree_level": "LL.B",
        "subject": "Luật Hiến pháp Việt Nam",
        "topic_title": "Chế độ Chính trị và Kiểm soát Quyền lực Nhà nước theo Hiến pháp 2013",
        "core_concept": "Quyền lực Nhà nước là Thống nhất, có sự phân công, phối hợp, kiểm soát",
        "theoretical_framework": "Quyền lực nhà nước là thống nhất, thuộc về nhân dân. Nhà nước pháp quyền XHCN Việt Nam không áp dụng học thuyết 'Tam quyền phân lập' tuyệt đối theo mô hình tư sản, mà áp dụng nguyên tắc Thống nhất quyền lực có sự phân công, phối hợp và kiểm soát giữa các cơ quan nhà nước trong việc thực hiện các quyền Lập pháp (Quốc hội), Hành pháp (Chính phủ) và Tư pháp (Tòa án nhân dân).",
        "legal_sources": ["Hiến pháp 2013 (Điều 2)", "Nghị quyết 27-NQ/TW 2022"],
        "source_university": "Trường Đại học Luật Hà Nội (HLU)"
    },
    {
        "degree_level": "LL.B",
        "subject": "Luật Dân sự - Phần Nghĩa vụ & Hợp đồng",
        "topic_title": "Bản chất Pháp lý của Thỏa thuận và Điều kiện Hiệu lực của Giao dịch Dân sự",
        "core_concept": "Tự do Cam kết, Thỏa thuận và Tự nguyện Giao kết Hợp đồng",
        "theoretical_framework": "Giao dịch dân sự thể hiện sự bày tỏ ý chí của các bên nhằm làm phát sinh, thay đổi hoặc chấm dứt quyền, nghĩa vụ dân sự. Điều kiện hiệu lực gồm: (1) Chủ thể có năng lực hành vi dân sự phù hợp; (2) Chủ thể hoàn toàn tự nguyện; (3) Mục đích và nội dung không vi phạm điều cấm của luật, không trái đạo đức xã hội; (4) Hình thức tuân thủ quy định khi luật có yêu cầu.",
        "legal_sources": ["Bộ luật Dân sự 2015 (Điều 116 - 129, Điều 385)"],
        "source_university": "Trường Đại học Luật TP.HCM (ULAW)"
    },
    {
        "degree_level": "LL.B",
        "subject": "Luật Hình sự - Phần Chung",
        "topic_title": "Lý luận về Lỗi trong Luật Hình sự Việt Nam",
        "core_concept": "Lỗi Cố ý (Trực tiếp / Gián tiếp) và Lỗi Vô ý (Vì quá tự tin / Do cẩu thả)",
        "theoretical_framework": "Lỗi là thái độ tâm lý của một người đối với hành vi nguy hiểm cho xã hội của mình và đối với hậu quả do hành vi đó gây ra. Phân loại: (1) Cố ý trực tiếp: Nhận thức rõ hành vi có hại, thấy trước hậu quả và mong muốn hậu quả xảy ra; (2) Cố ý gián tiếp: Nhận thức rõ hành vi có hại, thấy trước hậu quả, không mong muốn nhưng có ý thức để mặc cho hậu quả xảy ra; (3) Vô ý vì quá tự tin: Thấy trước hậu quả nhưng cho rằng hậu quả không xảy ra hoặc ngăn ngừa được; (4) Vô ý do cẩu thả: Không thấy trước hậu quả mặc dù phải thấy trước và có điều kiện thấy trước.",
        "legal_sources": ["Bộ luật Hình sự 2015 (Điều 10, Điều 11)"],
        "source_university": "Khoa Luật - Đại học Quốc gia Hà Nội (VNU-UL)"
    },
    {
        "degree_level": "LL.B",
        "subject": "Luật Hành chính & Tố tụng Hành chính",
        "topic_title": "Bản chất của Quyết định Hành chính và Hành vi Hành chính bị Khiếu kiện",
        "core_concept": "Quyết định Hành chính Mang tính Quyền lực - Đơn phương",
        "theoretical_framework": "Quyết định hành chính là văn bản do cơ quan hành chính nhà nước hoặc người có thẩm quyền ban hành để quyết định về một vấn đề cụ thể trong hoạt động quản lý hành chính nhà nước được áp dụng một lần đối với một hoặc một số đối tượng cụ thể. Tính chất quyền lực đơn phương làm phát sinh, thay đổi, hạn chế hoặc chấm dứt quyền, nghĩa vụ của cá nhân, tổ chức.",
        "legal_sources": ["Luật Tố tụng Hành chính 2015 (Điều 3)", "Luật Khiếu nại 2011"],
        "source_university": "Trường Đại học Luật Hà Nội (HLU)"
    },
    {
        "degree_level": "LL.B",
        "subject": "Luật Thương mại Quốc tế",
        "topic_title": "Các Nguyên tắc Cơ bản của WTO và Hợp đồng Mua bán Hàng hóa Quốc tế (CISG)",
        "core_concept": "Nguyên tắc Đối xử Tối huệ quốc (MFN) & Đối xử Quốc gia (NT)",
        "theoretical_framework": "Trong Luật Thương mại Quốc tế, nguyên tắc MFN (Most-Favoured-Nation) bắt buộc một nước thành viên phải dành sự đối xử không kém ưu đãi hơn cho hàng hóa của nước này so với hàng hóa của bất kỳ nước nào khác. Nguyên tắc NT (National Treatment) yêu cầu không phân biệt đối xử giữa hàng hóa nhập khẩu và hàng hóa sản xuất trong nước sau khi đã làm xong thủ tục thông quan.",
        "legal_sources": ["Công ước Viên 1980 về Hợp đồng Mua bán Hàng hóa Quốc tế (CISG)", "Hiệp định WTO"],
        "source_university": "Trường Đại học Luật TP.HCM (ULAW)"
    },

    # --- LL.M: THẠC SĨ LUẬT ---
    {
        "degree_level": "LL.M",
        "subject": "Triết học Pháp luật & Jurisprudence",
        "topic_title": "Pháp lý học Thực chứng (Legal Positivism) vs Pháp luật Tự nhiên (Natural Law)",
        "core_concept": "Mối quan hệ giữa Pháp luật và Đạo đức / Công lý",
        "theoretical_framework": "Trường phái Pháp luật Tự nhiên (Natural Law) cho rằng pháp luật gắn liền với công lý, đạo đức và bản chất con người; một quy định bất công không phải là pháp luật ('Lex injusta non est lex'). Ngược lại, Trường phái Pháp luật Thực chứng (Legal Positivism - Kelsen, Hart) tách biệt Pháp luật và Đạo đức ('Separation Thesis'), khẳng định hiệu lực của pháp luật phụ thuộc vào quy trình ban hành của cơ quan có thẩm quyền chứa đựng quyền lực tối cao.",
        "legal_sources": ["Chuyên đề Triết học Pháp luật Thạc sĩ", "Nghị quyết 27-NQ/TW 2022"],
        "source_university": "Viện Nhà nước và Pháp luật (VASS)"
    },
    {
        "degree_level": "LL.M",
        "subject": "Luật Dân sự & Tố tụng Dân sự Nâng cao",
        "topic_title": "Lý luận về Quyền Sở hữu Trí tuệ và Bảo hộ Tác phẩm do Trí tuệ Nhân tạo (AI) Tạo ra",
        "core_concept": "Tư cách Tác giả (Authorship) và Đột phá Quyền Tài sản Số",
        "theoretical_framework": "Theo học thuyết truyền thống, quyền tác giả chỉ phát sinh khi tác phẩm được sáng tạo trực tiếp bởi trí tuệ con người (Human Authorship). Sự xuất hiện của Generative AI đặt ra thách thức lý luận: Liệu nội dung do AI tạo ra thuộc về công chúng (Public Domain), thuộc về người tạo ra Prompt, hay nhà phát triển AI? Quan điểm pháp lý hiện đại nghiêng về việc bảo hộ phần đóng góp sáng tạo có dấu ấn con người hoặc tạo lập cơ chế chế định riêng (Sui Generis Right).",
        "legal_sources": ["Luật Sở hữu Trí tuệ 2005 (sửa đổi 2022)", "Công ước Berne"],
        "source_university": "Khoa Luật - Đại học Quốc gia Hà Nội (VNU-UL)"
    },
    {
        "degree_level": "LL.M",
        "subject": "Luật Kinh tế & Quản trị Doanh nghiệp",
        "topic_title": "Học thuyết Trách nhiệm Nghĩa vụ Trung thành và Cẩn trọng của Người Quản lý Doanh nghiệp (Fiduciary Duties)",
        "core_concept": "Nghĩa vụ Cẩn trọng (Duty of Care) & Nghĩa vụ Trung thành (Duty of Loyalty)",
        "theoretical_framework": "Trong quản trị công ty hiện đại, thành viên HĐQT, Giám đốc/Tổng giám đốc chịu nghĩa vụ ủy thác (Fiduciary Duty) đối với công ty và cổ đông. (1) Duty of Care: Thực hiện quyền hạn với sự cẩn trọng như một người khôn khéo; (2) Duty of Loyalty: Đặt lợi ích của công ty lên trên lợi ích cá nhân, không lợi dụng cơ hội kinh doanh của công ty.",
        "legal_sources": ["Luật Doanh nghiệp 2020 (Điều 165, Điều 166)"],
        "source_university": "Trường Đại học Luật Hà Nội (HLU)"
    },

    # --- Ph.D: TIẾN SĨ LUẬT ---
    {
        "degree_level": "Ph.D",
        "subject": "Phân tích Kinh tế về Pháp luật (Law & Economics)",
        "topic_title": "Định lý Coase, Chi phí Giao dịch và Hiệu quả Phân bổ trong Pháp luật Đất đai & Bất động sản",
        "core_concept": "Định lý Coase (Coase Theorem) & Chi phí Giao dịch (Transaction Costs)",
        "theoretical_framework": "Định lý Coase phát biểu rằng nếu chi phí giao dịch bằng 0, thị trường sẽ tự thương lượng để đạt đến kết quả phân bổ nguồn lực hiệu quả nhất bất kể sự phân bổ quyền ban đầu của pháp luật. Tuy nhiên, trong thực tiễn pháp luật đất đai, chi phí giao dịch thương lượng giữa chính quyền, doanh nghiệp và hộ gia đình là rất lớn. Do đó, vai trò của pháp luật là thiết kế quy định thu hồi đất, bồi thường giải phóng mặt bằng nhằm giảm thiểu chi phí giao dịch và tránh tổn thất xã hội (Deadweight loss).",
        "legal_sources": ["Luật Đất đai 2024", "Luật Kinh doanh Bất động sản 2023"],
        "source_university": "Viện Nhà nước và Pháp luật (VASS) / HLU"
    },
    {
        "degree_level": "Ph.D",
        "subject": "Hoàn thiện Thể chế Nhà nước Pháp quyền",
        "topic_title": "Kiểm soát Quyền lực Nhà nước và Phòng chống Tham nhũng, Tiêu cực trong Hoạt động Tư pháp",
        "core_concept": "Cơ chế Tự kiểm soát & Kiểm soát Nhánh Tư pháp độc lập",
        "theoretical_framework": "Luận án Tiến sĩ giải quyết bài toán độc lập tư pháp (Judicial Independence) gắn liền với trách nhiệm giải trình (Judicial Accountability). Tòa án xét xử độc lập và chỉ tuân theo pháp luật, đồng thời chịu sự kiểm soát thông qua cơ chế giám sát của Quốc hội, tranh tụng công khai và hoạt động kiểm sát của Viện Kiểm sát.",
        "legal_sources": ["Nghị quyết 27-NQ/TW 2022", "Luật Tổ chức Tòa án Nhân dân (sửa đổi)"],
        "source_university": "Trường Đại học Luật TP.HCM (ULAW)"
    }
]

# Danh sách Các Học thuyết Pháp lý Nền tảng (Legal Doctrines)
DOCTRINES_BATCH = [
    {
        "doctrine_name": "Cấu trúc Quy phạm Pháp luật 3 phần",
        "category": "Lý luận chung về Nhà nước và Pháp luật",
        "definition": "Mô hình lý thuyết chia QPPL thành Giả định (Conditional context), Quy định (Mandatory/Permissive behavior), và Chế tài (Sanction).",
        "origin_and_evolution": "Xuất phát từ trường phái Pháp luật Thực chứng Xô viết và được tiếp thu, phát triển trong Lý luận Pháp luật Việt Nam từ thập niên 1960.",
        "jurisprudence_stance": "Là công cụ phân tích chuẩn mực trong công tác lập pháp, giảng dạy và giải thích văn bản QPPL tại Việt Nam.",
        "counter_arguments": "Một số QPPL định nghĩa hoặc thủ tục không chứa đủ cả 3 phần (ví dụ: quy định định nghĩa không có chế tài trực tiếp).",
        "related_articles": "Luật Ban hành văn bản QPPL 2015"
    },
    {
        "doctrine_name": "Nguyên tắc Bất hồi tố (Non-retroactivity)",
        "category": "Lý luận Lập pháp & Luật Hình sự / Dân sự",
        "definition": "Văn bản QPPL không được quy định hiệu lực trở về trước đối với các hành vi xảy ra trước thời điểm văn bản có hiệu lực, trừ trường hợp quy định trách nhiệm nhẹ hơn.",
        "origin_and_evolution": "Nguyên tắc cốt lõi của Pháp luật La Mã ('Lex retro non agit') bảo đảm tính dự đoán được và an toàn pháp lý.",
        "jurisprudence_stance": "Được ghi nhận tại Điều 152 Luật Ban hành VBQPPL 2015 và Điều 7 Bộ luật Hình sự 2015.",
        "counter_arguments": "Ngoại lệ áp dụng hiệu lực trở về trước khi quy định trách nhiệm pháp lý nhẹ hơn hoặc loại bỏ trách nhiệm.",
        "related_articles": "Điều 152 Luật Ban hành VBQPPL 2015; Điều 7 Bộ luật Hình sự 2015"
    },
    {
        "doctrine_name": "Suy đoán Vô tội (Presumption of Innocence)",
        "category": "Luật Tố tụng Hình sự & Quyền con người",
        "definition": "Người bị buộc tội được coi là không có tội cho đến khi được chứng minh theo trình tự, thủ tục do luật định và có bản án kết tội của Tòa án đã có hiệu lực pháp luật.",
        "origin_and_evolution": "Nguyên tắc Hiến định quốc tế (Điều 11 Tuyên ngôn Quốc tế Nhân quyền 1948).",
        "jurisprudence_stance": "Được ghi nhận tại Điều 31 Hiến pháp 2013 và Điều 13 Bộ luật Tố tụng Hình sự 2015.",
        "counter_arguments": "Mọi nghi ngờ về lỗi không thể làm sáng tỏ phải được kết luận theo hướng có lợi cho người bị buộc tội.",
        "related_articles": "Điều 31 Hiến pháp 2013; Điều 13 BLTTHS 2015"
    }
]

# Danh sách Kỹ năng Thực hành 5 Chức danh Tư pháp (Judicial Practice Skills)
PRACTICE_SKILLS_BATCH = [
    {
        "role_name": "Luật sư",
        "skill_category": "Tham gia Tố tụng Hình sự & Bào chữa",
        "skill_title": "Kỹ năng Xây dựng Luận cứ Bào chữa cho Bị cáo tại Phiên tòa",
        "procedural_stage": "Xét xử Sơ thẩm / Phúc thẩm",
        "practical_guidelines": "Quy trình xây dựng Luận cứ bào chữa: (1) Tóm tắt diễn biến hành vi và quan điểm truy tố của Cáo trạng; (2) Đánh giá chứng cứ buộc tội của Cơ quan điều tra (về tính hợp pháp, tính khách quan và mối liên hệ); (3) Phân tích các tình tiết chưa đủ căn cứ cấu thành tội phạm hoặc tình tiết giảm nhẹ trách nhiệm hình sự (Điều 51 BLHS); (4) Đề xuất mức hình phạt hoặc loại bỏ trách nhiệm hình sự.",
        "legal_basis": "Luật Luật sư 2006 (sửa đổi 2012); Bộ luật Tố tụng Hình sự 2015 (Điều 73)",
        "source_academy": "Học viện Tư pháp (Bộ Tư pháp)"
    },
    {
        "role_name": "Kiểm sát viên",
        "skill_category": "Thực hành Quyền Công tố & Luận tội",
        "skill_title": "Kỹ năng Lập Cáo trạng và Trình bày Bản Luận tội tại Phiên tòa",
        "procedural_stage": "Truy tố & Xét xử",
        "practical_guidelines": "Quy trình thực hành quyền công tố: (1) Nghiên cứu toàn bộ hồ sơ vụ án do CQĐT chuyển sang; (2) Kiểm tra tính hợp pháp của các biên bản lấy lời khai, hỏi cung; (3) Lập Cáo trạng chi tiết khẳng định tội danh và khung hình phạt áp dụng; (4) Trình bày Bản Luận tội tại phiên tòa, theo dõi đối đáp tranh tụng với Luật sư bào chữa.",
        "legal_basis": "Bộ luật Tố tụng Hình sự 2015 (Điều 243, Điều 321)",
        "source_academy": "Trường Đại học Kiểm sát Hà Nội (VKSNDTC)"
    },
    {
        "role_name": "Thẩm phán",
        "skill_category": "Điều hành Phiên tòa & Tuyên án",
        "skill_title": "Kỹ năng Điều hành Tranh tụng và Soạn thảo Bản án Dân sự / Hình sự",
        "procedural_stage": "Xét xử & Nghị án",
        "practical_guidelines": "Quy trình Thẩm phán thực thi: (1) Lập hồ sơ nghiên cứu án, xác định quan hệ tranh chấp và pháp luật áp dụng; (2) Điều hành phiên tòa theo nguyên tắc tranh tụng công khai, lắng nghe bình đẳng giữa Kiểm sát viên, Luật sư và đương sự; (3) Áp dụng quy định pháp luật và Án lệ liên quan; (4) Soạn thảo Bản án gồm 4 phần (Mở đầu, Nội dung vụ án, Nhận định của Tòa án, Quyết định).",
        "legal_basis": "Nghị quyết 01/2017/NQ-HĐTP; Bộ luật Tố tụng Dân sự 2015; BLTTHS 2015",
        "source_academy": "Học viện Tòa án (TANDTC)"
    },
    {
        "role_name": "Chấp hành viên",
        "skill_category": "Cưỡng chế & Thi hành Án Dân sự",
        "skill_title": "Kỹ năng Xác minh Điều kiện Thi hành án và Kê biên Tài sản",
        "procedural_stage": "Thi hành án",
        "practical_guidelines": "Quy trình thi hành án dân sự: (1) Tống đạt quyết định thi hành án cho người phải thi hành án; (2) Tiến hành xác minh tài khoản ngân hàng, quyền sử dụng đất, bất động sản; (3) Ra quyết định cưỡng chế kê biên tài sản nếu người phải thi hành án cố tình không tự nguyện thi hành; (4) Tổ chức ký hợp đồng thẩm định giá và bán đấu giá tài sản kê biên.",
        "legal_basis": "Luật Thi hành án Dân sự 2008 (sửa đổi 2014)",
        "source_academy": "Học viện Tư pháp & Tổng cục THADS"
    },
    {
        "role_name": "Điều tra viên",
        "skill_category": "Điều tra Hình sự & Thu thập Chứng cứ",
        "skill_title": "Kỹ năng Hỏi cung Bị can và Thu thập, Bảo quản Dấu vết Hiện trường",
        "procedural_stage": "Điều tra",
        "practical_guidelines": "Quy trình kỹ năng Điều tra viên: (1) Lập sơ đồ khám nghiệm hiện trường, thu giữ và niêm phong dấu vết vật chứng; (2) Lập kế hoạch hỏi cung bị can, làm rõ mâu thuẫn trong lời khai; (3) Lập Bản Kết luận điều tra đề nghị truy tố chuyển Viện Kiểm sát.",
        "legal_basis": "Luật Tổ chức Cơ quan Điều tra Hình sự 2015; BLTTHS 2015",
        "source_academy": "Học viện Cảnh sát Nhân dân (Bộ Công an)"
    }
]

def harvest_data():
    if not os.path.exists(DB_PATH):
        logger.error(f"Không tìm thấy DB tại {DB_PATH}. Hãy chạy scripts/init_legal_theory_db.py trước.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    logger.info("⚡ Đang nạp dữ liệu Chuyên đề Học thuật & Giáo trình LL.B / LL.M / Ph.D...")
    
    for item in ACADEMIC_DATA_BATCH:
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
            f"{item['core_concept']} {item['theoretical_framework']}",
            item["subject"]
        ))

    logger.info("⚡ Đang nạp dữ liệu Học thuyết Pháp lý (Legal Doctrines)...")
    for doc in DOCTRINES_BATCH:
        try:
            cursor.execute("""
            INSERT INTO legal_doctrines (doctrine_name, category, definition, origin_and_evolution, jurisprudence_stance, counter_arguments, related_articles)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["doctrine_name"],
                doc["category"],
                doc["definition"],
                doc["origin_and_evolution"],
                doc["jurisprudence_stance"],
                doc["counter_arguments"],
                doc["related_articles"]
            ))
            doc_id = cursor.lastrowid
            cursor.execute("""
            INSERT INTO fts_theory (source_table, source_id, title, content, category)
            VALUES ('legal_doctrines', ?, ?, ?, ?)
            """, (
                doc_id,
                doc["doctrine_name"],
                f"{doc['definition']} {doc['jurisprudence_stance']}",
                doc["category"]
            ))
        except sqlite3.IntegrityError:
            pass

    logger.info("⚡ Đang nạp dữ liệu Kỹ năng Thực hành 5 Chức danh Tư pháp...")
    for sk in PRACTICE_SKILLS_BATCH:
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
            f"{sk['skill_category']} {sk['practical_guidelines']}",
            sk["role_name"]
        ))

    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM curriculum_topics")
    total_topics = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM legal_doctrines")
    total_doctrines = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM legal_practice_skills")
    total_skills = cursor.fetchone()[0]

    logger.info(f"🎉 Hoàn thành nạp dữ liệu! Giáo trình: {total_topics} | Học thuyết: {total_doctrines} | Kỹ năng Thực hành 5 Chức danh: {total_skills}")
    conn.close()

if __name__ == "__main__":
    harvest_data()
