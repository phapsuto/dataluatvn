#!/usr/bin/env python3
"""
scripts/init_legal_theory_db.py
================================
Khởi tạo và nạp dữ liệu nền tảng cho Cơ sở Dữ liệu Con: "Bộ Não Lý luận & Giáo trình Pháp luật Việt Nam" (legal_theory_mind.db).
Bao gồm các bảng:
- curriculum_topics (Giáo trình & Môn học LL.B/LL.M/Ph.D)
- legal_doctrines (Học thuyết, Khái niệm, Nguyên lý Pháp lý)
- academic_publications (Luận án Tiến sĩ, Bài báo Tạp chí Luật học)
- fts_theory (Search index FTS5 siêu tốc)
"""

import os
import sqlite3
import json

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"📦 Đang tạo bảng cho {DB_PATH}...")

    # 1. Bảng Giáo trình & Môn học
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS curriculum_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        degree_level TEXT NOT NULL,          -- LL.B, LL.M, Ph.D
        subject TEXT NOT NULL,               -- Tên môn học (vd: Lý luận chung về Nhà nước và Pháp luật)
        topic_title TEXT NOT NULL,           -- Tên bài giảng/chuyên đề
        core_concept TEXT NOT NULL,          -- Khái niệm trọng tâm
        theoretical_framework TEXT NOT NULL, -- Khung lý luận & phân tích
        legal_sources TEXT,                  -- Nguồn luật & căn cứ liên quan (JSON list)
        source_university TEXT DEFAULT 'Đại học Luật Hà Nội / ĐH Luật TP.HCM / ĐHQGHN',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Bảng Học thuyết, Khái niệm & Nguyên lý Pháp lý
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS legal_doctrines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctrine_name TEXT NOT NULL UNIQUE,  -- Tên học thuyết (vd: Cấu trúc Quy phạm Pháp luật 3 phần)
        category TEXT NOT NULL,              -- Lý luận chung, Dân sự, Hình sự, Hiến pháp...
        definition TEXT NOT NULL,            -- Định nghĩa & Bản chất
        origin_and_evolution TEXT,           -- Nguồn gốc & Lịch sử phát triển
        jurisprudence_stance TEXT NOT NULL,  -- Quan điểm pháp lý & Áp dụng tại Việt Nam
        counter_arguments TEXT,              -- Tranh luận học thuật & Các quan điểm khác
        related_articles TEXT                -- Căn cứ pháp lý QPPL liên quan
    );
    """)

    # 3. Bảng Công trình Nghiên cứu & Luận án Tiến sĩ
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS academic_publications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        publication_type TEXT NOT NULL,      -- Luận án Tiến sĩ, Tạp chí Luật học, Sách Chuyên khảo
        title TEXT NOT NULL,                 -- Tên đề tài / bài báo
        author TEXT NOT NULL,                -- Tác giả / Nghiên cứu sinh / GS.TS
        institution TEXT NOT NULL,           -- HLU, ULAW, VNU-UL, VASS
        year INTEGER,                        -- Năm xuất bản / Bảo vệ
        abstract_summary TEXT NOT NULL,      -- Tóm tắt kết quả nghiên cứu & Đóng góp mới
        theoretical_contributions TEXT,      -- Giá trị đóng góp lý luận
        keywords TEXT                        -- Từ khóa chính (comma separated)
    );
    """)

    # 4. Bảng Kỹ năng Thực hành 5 Chức danh Tư pháp (Luật sư, KSV, Thẩm phán, Chấp hành viên, Điều tra viên)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS legal_practice_skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_name TEXT NOT NULL,             -- Luật sư, Kiểm sát viên, Thẩm phán, Chấp hành viên, Điều tra viên
        skill_category TEXT NOT NULL,        -- Bào chữa, Luận tội, Tuyên án, Kê biên, Hỏi cung...
        skill_title TEXT NOT NULL,           -- Tên kỹ năng thao tác
        procedural_stage TEXT NOT NULL,      -- Khởi tố, Điều tra, Truy tố, Xét xử, Thi hành án
        practical_guidelines TEXT NOT NULL,  -- Hướng dẫn quy trình nghiệp vụ thực hành
        legal_basis TEXT,                    -- Căn cứ pháp lý quy định (BLTTHS, BLTTDS, Luật Luật sư...)
        source_academy TEXT DEFAULT 'Học viện Tư pháp / Học viện Tòa án / ĐH Kiểm sát / HV Cảnh sát'
    );
    """)

    # 5. Bảng FTS5 Toàn văn
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_theory USING fts5(
        source_table,
        source_id,
        title,
        content,
        category,
        tokenize = 'unicode61'
    );
    """)

    conn.commit()
    print("✅ Đã tạo bảng thành công.")
    return conn

def seed_initial_data(conn):
    cursor = conn.cursor()
    
    # Kiểm tra xem đã có dữ liệu chưa
    cursor.execute("SELECT COUNT(*) FROM curriculum_topics")
    if cursor.fetchone()[0] > 0:
        print("ℹ️ Dữ liệu khởi tạo đã tồn tại. Bỏ qua seeding.")
        return

    print("🌱 Đang nạp dữ liệu giáo trình & học thuyết nền tảng...")

    topics = [
        # LL.B - Lý luận chung
        (
            "LL.B",
            "Lý luận chung về Nhà nước và Pháp luật",
            "Cấu trúc Quy phạm Pháp luật và Cơ chế Điều chỉnh Pháp luật",
            "Quy phạm Pháp luật (QPPL)",
            "Quy phạm pháp luật là quy tắc hành vi chung, do Nhà nước ban hành hoặc thừa nhận, thể hiện chí ý của Nhà nước và được Nhà nước bảo đảm thực hiện. Cấu trúc truyền thống gồm 3 bộ phận: (1) Giả định - Nêu rõ điều kiện, hoàn cảnh; (2) Quy định - Nêu cách ứng xử được làm, không được làm hoặc phải làm; (3) Chế tài - Biện pháp cưỡng chế nhà nước khi vi phạm.",
            json.dumps(["Luật Ban hành văn bản QPPL 2015 (sửa đổi 2020)"]),
            "Trường Đại học Luật Hà Nội"
        ),
        (
            "LL.B",
            "Lý luận chung về Nhà nước và Pháp luật",
            "Cấu thành Vi phạm Pháp luật và Trách nhiệm Pháp lý",
            "Vi phạm Pháp luật & Trách nhiệm Pháp lý",
            "Vi phạm pháp luật là hành vi trái pháp luật, có lỗi, do chủ thể có năng lực trách nhiệm pháp lý thực hiện, xâm hại đến các quan hệ xã hội được pháp luật bảo vệ. Cấu thành vi phạm pháp luật gồm 4 yếu tố bắt buộc: (1) Mặt khách quan (Hành vi, Hậu quả, Mối quan hệ nguyên nhân - kết quả); (2) Mặt chủ quan (Lỗi cố ý/vô ý, Động cơ, Mục đích); (3) Chủ thể; (4) Khách thể.",
            json.dumps(["Bộ luật Hình sự 2015", "Bộ luật Dân sự 2015", "Luật Xử lý vi phạm hành chính 2012"]),
            "Trường Đại học Luật TP.HCM"
        ),
        # LL.M - Thạc sĩ
        (
            "LL.M",
            "Triết học Pháp luật & Jurisprudence",
            "Bản chất và Giá trị của Pháp luật trong Nhà nước Pháp quyền XHCN",
            "Nhà nước Pháp quyền XHCN & Triết học Pháp luật",
            "Pháp luật trong Nhà nước pháp quyền XHCN Việt Nam mang bản chất giai cấp công nhân và tính nhân dân, tính dân tộc sâu sắc. Pháp luật là công cụ kiểm soát quyền lực nhà nước, bảo đảm quyền con người, quyền công dân, hướng tới giá trị Công bằng, Bình đẳng và Dân chủ.",
            json.dumps(["Hiến pháp 2013", "Nghị quyết 27-NQ/TW 2022 về Tiếp tục xây dựng và hoàn thiện Nhà nước pháp quyền XHCN"]),
            "Viện Nhà nước và Pháp luật (VASS)"
        ),
        (
            "LL.M",
            "Luật Dân sự & Tố tụng Dân sự Nâng cao",
            "Lý luận về Trách nhiệm Bồi thường Thiệt hại Ngoài Hợp đồng",
            "Trách nhiệm Bồi thường Thiệt hại Ngoài Hợp đồng",
            "Trách nhiệm bồi thường thiệt hại ngoài hợp đồng phát sinh khi có hành vi trái pháp luật gây thiệt hại, có thiệt hại thực tế xảy ra và có mối quan hệ nhân quả giữa hành vi trái pháp luật với thiệt hại. Yếu tố lỗi là căn cứ quan trọng trừ trường hợp pháp luật có quy định khác (bồi thường do nguồn nguy hiểm cao độ gây ra).",
            json.dumps(["Bộ luật Dân sự 2015 (Điều 584 - 608)", "Nghị quyết 02/2022/NQ-HĐTP"]),
            "Khoa Luật - ĐHQGHN"
        ),
        # Ph.D - Tiến sĩ
        (
            "Ph.D",
            "Phân tích Kinh tế về Pháp luật (Law & Economics)",
            "Ứng dụng Phân tích Kinh tế trong Thiết kế Chính sách và Pháp luật Đất đai",
            "Economic Analysis of Law & Transaction Costs",
            "Phân tích Kinh tế về Pháp luật sử dụng các công cụ kinh tế học (Định lý Coase, Chi phí giao dịch, Hiệu quả Pareto) để đánh giá tác động của quy phạm pháp luật. Áp dụng vào Luật Đất đai giúp tối ưu hóa việc phân bổ tài nguyên đất đai, giảm thiểu chi phí giao dịch thương lượng và bảo đảm hài hòa lợi ích giữa Nhà nước, Người sử dụng đất và Nhà đầu tư.",
            json.dumps(["Luật Đất đai 2024", "Nghị quyết 18-NQ/TW 2022"]),
            "Trường Đại học Luật Hà Nội"
        )
    ]

    cursor.executemany("""
    INSERT INTO curriculum_topics (degree_level, subject, topic_title, core_concept, theoretical_framework, legal_sources, source_university)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, topics)

    # Nạp FTS5
    cursor.execute("""
    INSERT INTO fts_theory (source_table, source_id, title, content, category)
    SELECT 'curriculum_topics', id, topic_title, core_concept || ' ' || theoretical_framework, subject
    FROM curriculum_topics
    """)

    conn.commit()
    print("✅ Đã nạp thành công dữ liệu khởi tạo cho legal_theory_mind.db.")

if __name__ == "__main__":
    connection = init_db()
    seed_initial_data(connection)
    connection.close()
