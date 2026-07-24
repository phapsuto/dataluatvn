#!/usr/bin/env python3
"""
scripts/build_curriculum_knowledge.py
======================================
BƯỚC 1: Sinh Tri thức Giáo trình 14 Môn Luật Cốt lõi bằng LLM Knowledge Distillation.
Sử dụng FPT Cloud API (Gemma-4-31B-it) để tổng hợp kiến thức chuẩn cho từng chủ đề,
rồi lưu vào bảng `curriculum_topics` trong `legal_theory_mind.db`.

BƯỚC 2: Sinh Học thuyết & Nguyên tắc Pháp luật vào bảng `legal_doctrines`.

Phương pháp: Knowledge Distillation — dùng LLM đã được train trên hàng triệu giáo trình luật
để tổng hợp kiến thức pháp luật Việt Nam chuẩn mực. Không cào website, không bịa dữ liệu.
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import logging
from datetime import datetime

# Load .env
from dotenv import load_dotenv
load_dotenv("/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/.env")

import litellm
litellm.telemetry = False
litellm.drop_params = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("CurriculumBuilder")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

FPT_API_KEY = os.environ.get("FPT_CLOUD_API_KEY", "")
FPT_MODEL = "custom_openai/gemma-4-31B-it"
FPT_API_BASE = "https://mkp-api.fptcloud.com/v1"

# ══════════════════════════════════════════════════════════════
# 14 MÔN LUẬT CỐT LÕI + CHỦ ĐỀ CHI TIẾT
# ══════════════════════════════════════════════════════════════

CURRICULUM = {
    "Lý luận Nhà nước và Pháp luật": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Nguồn gốc, bản chất và hình thức nhà nước",
            "Bộ máy nhà nước CHXHCN Việt Nam",
            "Bản chất, chức năng và vai trò của pháp luật",
            "Quy phạm pháp luật và hệ thống pháp luật Việt Nam",
            "Quan hệ pháp luật và sự kiện pháp lý",
            "Thực hiện pháp luật và áp dụng pháp luật",
            "Vi phạm pháp luật và trách nhiệm pháp lý",
            "Ý thức pháp luật và pháp chế XHCN",
        ]
    },
    "Luật Hiến pháp": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Hiến pháp trong hệ thống pháp luật Việt Nam - vị trí tối cao",
            "Chế độ chính trị và quyền lực nhà nước theo Hiến pháp 2013",
            "Quyền con người và quyền công dân cơ bản",
            "Quốc hội - Cơ quan quyền lực nhà nước cao nhất",
            "Chủ tịch nước, Chính phủ và Thủ tướng Chính phủ",
            "Tòa án nhân dân và Viện kiểm sát nhân dân",
            "Chính quyền địa phương theo Hiến pháp 2013",
            "Bầu cử và trưng cầu ý dân",
        ]
    },
    "Luật Hành chính": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Khái niệm, đối tượng và phương pháp điều chỉnh của Luật Hành chính",
            "Cơ quan hành chính nhà nước và công chức, viên chức",
            "Thủ tục hành chính và cải cách thủ tục hành chính",
            "Vi phạm hành chính và xử phạt vi phạm hành chính",
            "Khiếu nại, tố cáo hành chính",
            "Tố tụng hành chính - Kiện quyết định hành chính tại Tòa án",
            "Quản lý nhà nước theo ngành và lãnh thổ",
            "Trách nhiệm bồi thường của Nhà nước",
        ]
    },
    "Luật Dân sự": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Chủ thể quan hệ pháp luật dân sự (cá nhân, pháp nhân)",
            "Quyền sở hữu và các quyền khác đối với tài sản",
            "Nghĩa vụ dân sự và hợp đồng dân sự",
            "Bồi thường thiệt hại ngoài hợp đồng",
            "Thừa kế theo di chúc và thừa kế theo pháp luật",
            "Giao dịch dân sự và hợp đồng vô hiệu",
            "Đại diện, giám hộ và ủy quyền",
            "Thời hiệu và thời hạn trong pháp luật dân sự",
        ]
    },
    "Luật Hình sự": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Tội phạm: khái niệm, phân loại và cấu thành tội phạm",
            "Các giai đoạn thực hiện tội phạm và đồng phạm",
            "Hình phạt: mục đích, hệ thống và nguyên tắc quyết định hình phạt",
            "Tình tiết giảm nhẹ, tăng nặng trách nhiệm hình sự",
            "Các tội xâm phạm tính mạng, sức khỏe, nhân phẩm con người",
            "Các tội xâm phạm quyền sở hữu (trộm cắp, lừa đảo, cướp tài sản)",
            "Các tội phạm về ma túy, tham nhũng và chức vụ",
            "Miễn trách nhiệm hình sự, miễn hình phạt và xóa án tích",
            "Trách nhiệm hình sự của pháp nhân thương mại",
        ]
    },
    "Luật Tố tụng Dân sự": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Nguyên tắc cơ bản của tố tụng dân sự Việt Nam",
            "Thẩm quyền xét xử dân sự của Tòa án các cấp",
            "Chứng cứ và chứng minh trong tố tụng dân sự",
            "Thủ tục sơ thẩm vụ án dân sự",
            "Thủ tục phúc thẩm và giám đốc thẩm, tái thẩm",
            "Thủ tục giải quyết việc dân sự (ly hôn thuận tình, tuyên bố mất tích...)",
            "Biện pháp khẩn cấp tạm thời",
            "Thi hành bản án, quyết định dân sự",
        ]
    },
    "Luật Tố tụng Hình sự": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Nguyên tắc cơ bản của tố tụng hình sự (suy đoán vô tội, tranh tụng, độc lập xét xử)",
            "Khởi tố vụ án hình sự và khởi tố bị can",
            "Giai đoạn điều tra: thẩm quyền, biện pháp ngăn chặn, hỏi cung bị can",
            "Giai đoạn truy tố: VKS quyết định truy tố hay không truy tố",
            "Xét xử sơ thẩm vụ án hình sự tại Tòa án",
            "Xét xử phúc thẩm, giám đốc thẩm, tái thẩm vụ án hình sự",
            "Người tham gia tố tụng (bị cáo, bị hại, người bào chữa, người bảo vệ quyền lợi)",
            "Thủ tục rút gọn và thủ tục đặc biệt trong tố tụng hình sự",
        ]
    },
    "Luật Đất đai": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Chế độ sở hữu đất đai toàn dân và quyền sử dụng đất",
            "Các loại đất và quy hoạch sử dụng đất",
            "Giao đất, cho thuê đất và chuyển mục đích sử dụng đất",
            "Chuyển nhượng, tặng cho, thừa kế quyền sử dụng đất",
            "Thu hồi đất, bồi thường và tái định cư",
            "Giấy chứng nhận quyền sử dụng đất (Sổ đỏ)",
            "Giải quyết tranh chấp đất đai",
            "Xử lý vi phạm pháp luật về đất đai",
        ]
    },
    "Luật Lao động": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Hợp đồng lao động: giao kết, thực hiện, chấm dứt",
            "Tiền lương, tiền công và chế độ phúc lợi",
            "Thời giờ làm việc, thời giờ nghỉ ngơi",
            "Kỷ luật lao động và trách nhiệm vật chất",
            "Bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp",
            "Giải quyết tranh chấp lao động và đình công",
            "Lao động nữ, lao động chưa thành niên và lao động đặc thù",
            "Tổ chức đại diện người lao động (Công đoàn)",
        ]
    },
    "Luật Thương mại và Doanh nghiệp": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Thành lập, tổ chức và quản lý doanh nghiệp (Công ty TNHH, Công ty CP, DN tư nhân)",
            "Quyền và nghĩa vụ của cổ đông, thành viên công ty",
            "Hợp đồng thương mại và chế tài thương mại",
            "Mua bán hàng hóa quốc tế và Incoterms",
            "Phá sản doanh nghiệp: điều kiện, thủ tục và hậu quả pháp lý",
            "Cạnh tranh và chống cạnh tranh không lành mạnh",
            "Trọng tài thương mại và giải quyết tranh chấp thương mại",
            "Đầu tư nước ngoài tại Việt Nam",
        ]
    },
    "Luật Hôn nhân và Gia đình": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Điều kiện kết hôn và các trường hợp cấm kết hôn",
            "Quyền và nghĩa vụ giữa vợ chồng",
            "Chế độ tài sản chung, tài sản riêng của vợ chồng",
            "Ly hôn: điều kiện, thủ tục thuận tình và đơn phương",
            "Quyền nuôi con sau ly hôn và cấp dưỡng",
            "Quan hệ hôn nhân có yếu tố nước ngoài",
        ]
    },
    "Luật Thi hành án Dân sự": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Nguyên tắc và thủ tục thi hành án dân sự",
            "Quyền và nghĩa vụ của Chấp hành viên",
            "Biện pháp cưỡng chế thi hành án dân sự",
            "Kê biên, xử lý tài sản để thi hành án",
            "Phong tỏa tài khoản, tài sản và khấu trừ thu nhập",
            "Miễn, giảm và đình chỉ thi hành án",
        ]
    },
    "Tư pháp Quốc tế": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Xung đột pháp luật và quy tắc chọn luật áp dụng",
            "Thẩm quyền tài phán quốc tế của Tòa án Việt Nam",
            "Công nhận và cho thi hành bản án, quyết định của Tòa án nước ngoài",
            "Tương trợ tư pháp quốc tế",
            "Hợp đồng quốc tế và Công ước Viên 1980 về mua bán hàng hóa quốc tế",
            "Trọng tài thương mại quốc tế",
        ]
    },
    "Luật Sở hữu trí tuệ": {
        "degree": "Cử nhân Luật",
        "topics": [
            "Quyền tác giả và quyền liên quan",
            "Sáng chế, giải pháp hữu ích và kiểu dáng công nghiệp",
            "Nhãn hiệu, tên thương mại và chỉ dẫn địa lý",
            "Bí mật kinh doanh và chống cạnh tranh không lành mạnh trong SHTT",
            "Chuyển giao quyền SHTT (License, nhượng quyền thương mại)",
            "Xử lý xâm phạm quyền SHTT",
        ]
    },
}

# ══════════════════════════════════════════════════════════════
# HỌC THUYẾT & NGUYÊN TẮC PHÁP LUẬT
# ══════════════════════════════════════════════════════════════

LEGAL_DOCTRINES = [
    # Nguyên tắc Hiến định
    {"name": "Suy đoán vô tội (Presumption of Innocence)", "category": "Nguyên tắc Hiến định", "related_articles": "Điều 31 Hiến pháp 2013, Điều 13 BLTTHS 2015"},
    {"name": "Bình đẳng trước pháp luật", "category": "Nguyên tắc Hiến định", "related_articles": "Điều 16 Hiến pháp 2013"},
    {"name": "Pháp quyền XHCN - Nhà nước quản lý xã hội bằng pháp luật", "category": "Nguyên tắc Hiến định", "related_articles": "Điều 2, Điều 8 Hiến pháp 2013"},
    {"name": "Quyền con người không bị hạn chế trừ trường hợp luật định", "category": "Nguyên tắc Hiến định", "related_articles": "Điều 14 Khoản 2 Hiến pháp 2013"},
    {"name": "Không ai bị kết tội hai lần về cùng một hành vi (Ne bis in idem)", "category": "Nguyên tắc Hiến định", "related_articles": "Điều 31 Khoản 3 Hiến pháp 2013"},
    # Nguyên tắc Dân sự
    {"name": "Thiện chí và Trung thực (Good Faith)", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 3 Khoản 3 BLDS 2015"},
    {"name": "Tự do ý chí và tự do thỏa thuận (Freedom of Contract)", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 3 Khoản 2 BLDS 2015"},
    {"name": "Bình đẳng các chủ thể dân sự", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 3 Khoản 1 BLDS 2015"},
    {"name": "Bảo vệ người thứ ba ngay tình", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 133 BLDS 2015"},
    {"name": "Tôn trọng lợi ích Nhà nước, lợi ích công cộng và quyền lợi hợp pháp của người khác", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 3 Khoản 4 BLDS 2015"},
    {"name": "Không ai được tự xử (Nemo judex in causa sua)", "category": "Nguyên tắc Dân sự", "related_articles": "Điều 14 BLDS 2015"},
    # Nguyên tắc Hình sự
    {"name": "Nullum crimen sine lege - Không có tội nếu không có luật quy định", "category": "Nguyên tắc Hình sự", "related_articles": "Điều 2 BLHS 2015"},
    {"name": "Cá thể hóa hình phạt (Individualization of Punishment)", "category": "Nguyên tắc Hình sự", "related_articles": "Điều 3 Khoản 2, Điều 50 BLHS 2015"},
    {"name": "Nhân đạo trong Luật Hình sự", "category": "Nguyên tắc Hình sự", "related_articles": "Điều 3 Khoản 5 BLHS 2015"},
    {"name": "Không hồi tố bất lợi (Non-retroactivity of Criminal Law)", "category": "Nguyên tắc Hình sự", "related_articles": "Điều 7 BLHS 2015"},
    {"name": "Trách nhiệm do lỗi (Mens Rea / Guilty Mind)", "category": "Nguyên tắc Hình sự", "related_articles": "Điều 10, 11 BLHS 2015 (Cố ý, Vô ý)"},
    # Nguyên tắc Tố tụng
    {"name": "Tranh tụng công khai tại phiên tòa", "category": "Nguyên tắc Tố tụng", "related_articles": "Điều 26 BLTTHS 2015, Điều 12 BLTTDS 2015"},
    {"name": "Xét xử hai cấp (Sơ thẩm + Phúc thẩm)", "category": "Nguyên tắc Tố tụng", "related_articles": "Điều 27 BLTTHS 2015, Điều 17 BLTTDS 2015"},
    {"name": "Độc lập xét xử - Thẩm phán chỉ tuân theo pháp luật", "category": "Nguyên tắc Tố tụng", "related_articles": "Điều 23 BLTTHS 2015, Điều 12 BLTTDS 2015"},
    {"name": "Bảo đảm quyền bào chữa của bị can, bị cáo", "category": "Nguyên tắc Tố tụng", "related_articles": "Điều 16 BLTTHS 2015"},
    {"name": "Bảo đảm quyền khiếu nại, tố cáo trong tố tụng", "category": "Nguyên tắc Tố tụng", "related_articles": "Điều 32 BLTTHS 2015"},
    # Nguyên tắc Hành chính
    {"name": "Pháp chế XHCN trong quản lý hành chính", "category": "Nguyên tắc Hành chính", "related_articles": "Điều 8 Hiến pháp 2013, Luật Tổ chức Chính phủ 2015"},
    {"name": "Tập trung dân chủ", "category": "Nguyên tắc Hành chính", "related_articles": "Điều 8 Hiến pháp 2013"},
    {"name": "Quản lý theo ngành kết hợp quản lý theo lãnh thổ", "category": "Nguyên tắc Hành chính", "related_articles": "Luật Tổ chức Chính quyền địa phương 2015"},
    # Nguyên tắc Đất đai
    {"name": "Đất đai thuộc sở hữu toàn dân do Nhà nước đại diện chủ sở hữu", "category": "Nguyên tắc Đất đai", "related_articles": "Điều 53 Hiến pháp 2013, Điều 4 Luật Đất đai 2024"},
    # Nguyên tắc Lao động
    {"name": "Bảo vệ quyền lợi hợp pháp của người lao động", "category": "Nguyên tắc Lao động", "related_articles": "Điều 4 BLLĐ 2019"},
    {"name": "Tự do việc làm và tự do tuyển dụng lao động", "category": "Nguyên tắc Lao động", "related_articles": "Điều 4 Khoản 1 BLLĐ 2019"},
]

def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """Gọi FPT Cloud LLM API."""
    try:
        resp = litellm.completion(
            model=FPT_MODEL,
            api_base=FPT_API_BASE,
            api_key=FPT_API_KEY,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM API Error: {e}")
        return ""

def setup_db():
    """Tạo/kiểm tra schema bảng."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS curriculum_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        degree_level TEXT,
        subject TEXT,
        topic_title TEXT,
        core_concept TEXT,
        theoretical_framework TEXT,
        key_articles TEXT,
        source_university TEXT DEFAULT 'Knowledge Distillation (LLM)',
        content_hash TEXT UNIQUE,
        created_at TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS legal_doctrines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctrine_name TEXT UNIQUE,
        category TEXT,
        definition TEXT,
        jurisprudence_stance TEXT,
        related_articles TEXT,
        content_hash TEXT UNIQUE,
        created_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def build_curriculum():
    """Bước 1: Sinh tri thức giáo trình 14 môn luật."""
    logger.info("=" * 80)
    logger.info("🎓 BƯỚC 1: SINH TRI THỨC GIÁO TRÌNH 14 MÔN LUẬT CỐT LÕI")
    logger.info("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    total_saved = 0
    total_subjects = len(CURRICULUM)
    
    for subj_idx, (subject, info) in enumerate(CURRICULUM.items(), 1):
        degree = info["degree"]
        topics = info["topics"]
        logger.info(f"\n📚 [{subj_idx}/{total_subjects}] Môn: {subject} ({len(topics)} chủ đề)")
        
        for topic_idx, topic in enumerate(topics, 1):
            # Check if already exists
            check_hash = hashlib.md5(f"{subject}:{topic}".encode()).hexdigest()
            c.execute("SELECT id FROM curriculum_topics WHERE content_hash=?", (check_hash,))
            if c.fetchone():
                logger.info(f"   ⏭️ [{topic_idx}/{len(topics)}] Đã có: {topic[:50]}")
                continue
            
            prompt = f"""Bạn là Giáo sư Luật tại Đại học Luật Hà Nội. Hãy viết bài giảng ngắn gọn nhưng chính xác về chủ đề sau trong môn {subject}:

Chủ đề: "{topic}"

YÊU CẦU:
1. Phần "KHÁI NIỆM CỐT LÕI" (300-500 từ): Định nghĩa, đặc điểm, phân loại. Dùng thuật ngữ pháp lý Việt Nam chuẩn.
2. Phần "HỌC THUYẾT & NGUYÊN TẮC NỀN TẢNG" (400-800 từ): Cơ sở lý luận, các học thuyết/trường phái liên quan, nguyên tắc áp dụng trong thực tiễn pháp luật Việt Nam.
3. Phần "CĂN CỨ PHÁP LÝ TRỌNG TÂM": Liệt kê 3-8 Điều luật quan trọng nhất cần nắm (ghi rõ Số hiệu VBQPPL, Điều, Khoản).

Viết bằng tiếng Việt, chuyên sâu, chính xác theo pháp luật Việt Nam hiện hành."""

            result = call_llm(prompt, max_tokens=1800)
            if not result or len(result) < 200:
                logger.warning(f"   ⚠️ LLM trả về rỗng cho: {topic}")
                continue
            
            # Parse sections
            core_concept = ""
            framework = ""
            key_articles = ""
            
            sections = result.split("\n")
            current_section = ""
            for line in sections:
                line_lower = line.lower().strip()
                if "khái niệm" in line_lower and ("cốt lõi" in line_lower or "#" in line):
                    current_section = "concept"
                    continue
                elif "học thuyết" in line_lower or "nguyên tắc nền tảng" in line_lower or "lý luận" in line_lower:
                    current_section = "framework"
                    continue
                elif "căn cứ pháp lý" in line_lower or "điều luật" in line_lower:
                    current_section = "articles"
                    continue
                
                if current_section == "concept":
                    core_concept += line + "\n"
                elif current_section == "framework":
                    framework += line + "\n"
                elif current_section == "articles":
                    key_articles += line + "\n"
            
            # If parsing failed, use full text as framework
            if not core_concept.strip() and not framework.strip():
                framework = result
            
            try:
                c.execute("""
                INSERT OR IGNORE INTO curriculum_topics
                (degree_level, subject, topic_title, core_concept, theoretical_framework, legal_sources, source_university, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    degree, subject, topic,
                    core_concept.strip() or result[:1500],
                    framework.strip() or result,
                    key_articles.strip(),
                    "Knowledge Distillation (FPT Cloud Gemma-4-31B-it)",
                    check_hash,
                    datetime.now().isoformat()
                ))
                
                if c.rowcount > 0:
                    # Index in FTS
                    row_id = c.lastrowid
                    fts_title = f"📚 {subject} | {topic}"
                    fts_content = f"{core_concept}\n{framework}\n{key_articles}".strip() or result
                    c.execute("""
                    INSERT INTO fts_theory (source_table, source_id, title, content, category)
                    VALUES ('curriculum_topics', ?, ?, ?, ?)
                    """, (row_id, fts_title, fts_content[:15000], subject))
                    
                    conn.commit()
                    total_saved += 1
                    word_count = len(result.split())
                    logger.info(f"   ✅ [{topic_idx}/{len(topics)}] {topic[:50]} | {word_count} từ")
            except Exception as e:
                logger.error(f"   ❌ DB Error: {e}")
            
            time.sleep(1.5)  # Rate limiting
    
    conn.close()
    logger.info(f"\n{'='*80}")
    logger.info(f"🎉 HOÀN THÀNH: Đã sinh và lưu {total_saved} chủ đề giáo trình vào curriculum_topics!")
    logger.info(f"{'='*80}")
    return total_saved

def build_doctrines():
    """Bước 2: Sinh học thuyết & nguyên tắc pháp luật."""
    logger.info("\n" + "=" * 80)
    logger.info("⚖️ BƯỚC 2: SINH HỌC THUYẾT & NGUYÊN TẮC PHÁP LUẬT")
    logger.info("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    total_saved = 0
    
    for idx, doctrine in enumerate(LEGAL_DOCTRINES, 1):
        name = doctrine["name"]
        category = doctrine["category"]
        related = doctrine["related_articles"]
        
        # Check if exists
        c.execute("SELECT id FROM legal_doctrines WHERE doctrine_name=?", (name,))
        if c.fetchone():
            logger.info(f"   ⏭️ [{idx}/{len(LEGAL_DOCTRINES)}] Đã có: {name[:50]}")
            continue
        
        prompt = f"""Bạn là Giáo sư Luật tại Đại học Luật Hà Nội. Hãy giảng giải về nguyên tắc/học thuyết pháp luật sau:

Tên: "{name}"
Thuộc nhóm: {category}
Căn cứ pháp lý: {related}

YÊU CẦU:
1. ĐỊNH NGHĨA (200-300 từ): Nội hàm, ý nghĩa và nguồn gốc của nguyên tắc/học thuyết này.
2. QUAN ĐIỂM PHÁP LÝ (300-500 từ): Cách áp dụng trong thực tiễn tư pháp Việt Nam, ví dụ minh họa cụ thể, mối quan hệ với các nguyên tắc khác.

Viết bằng tiếng Việt, chuyên sâu, chính xác."""

        result = call_llm(prompt, max_tokens=1200)
        if not result or len(result) < 100:
            logger.warning(f"   ⚠️ LLM trả về rỗng cho: {name}")
            continue
        
        # Parse definition and stance
        definition = ""
        stance = ""
        current = ""
        for line in result.split("\n"):
            line_lower = line.lower().strip()
            if "định nghĩa" in line_lower or "nội hàm" in line_lower:
                current = "def"
                continue
            elif "quan điểm" in line_lower or "áp dụng" in line_lower or "thực tiễn" in line_lower:
                current = "stance"
                continue
            if current == "def":
                definition += line + "\n"
            elif current == "stance":
                stance += line + "\n"
        
        if not definition.strip():
            definition = result[:len(result)//2]
        if not stance.strip():
            stance = result[len(result)//2:]
        
        content_hash = hashlib.md5(f"doctrine:{name}".encode()).hexdigest()
        
        try:
            c.execute("""
            INSERT OR IGNORE INTO legal_doctrines
            (doctrine_name, category, definition, jurisprudence_stance, related_articles, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name, category,
                definition.strip(),
                stance.strip(),
                related,
                content_hash,
                datetime.now().isoformat()
            ))
            
            if c.rowcount > 0:
                row_id = c.lastrowid
                fts_title = f"⚖️ {category}: {name}"
                fts_content = f"{definition}\n{stance}".strip()
                c.execute("""
                INSERT INTO fts_theory (source_table, source_id, title, content, category)
                VALUES ('legal_doctrines', ?, ?, ?, ?)
                """, (row_id, fts_title, fts_content[:10000], category))
                
                conn.commit()
                total_saved += 1
                logger.info(f"   ✅ [{idx}/{len(LEGAL_DOCTRINES)}] {name[:60]}")
        except Exception as e:
            logger.error(f"   ❌ DB Error: {e}")
        
        time.sleep(1.5)
    
    conn.close()
    logger.info(f"\n{'='*80}")
    logger.info(f"🎉 HOÀN THÀNH: Đã sinh và lưu {total_saved} học thuyết/nguyên tắc vào legal_doctrines!")
    logger.info(f"{'='*80}")
    return total_saved

if __name__ == "__main__":
    setup_db()
    
    logger.info("🚀 BẮT ĐẦU SINH TRI THỨC PHÁP LUẬT BẰNG LLM KNOWLEDGE DISTILLATION")
    logger.info(f"   Model: {FPT_MODEL}")
    logger.info(f"   API: {FPT_API_BASE}")
    logger.info(f"   DB: {DB_PATH}")
    logger.info(f"   Tổng số môn: {len(CURRICULUM)}")
    logger.info(f"   Tổng số chủ đề: {sum(len(info['topics']) for info in CURRICULUM.values())}")
    logger.info(f"   Tổng số học thuyết: {len(LEGAL_DOCTRINES)}")
    
    t1 = build_curriculum()
    t2 = build_doctrines()
    
    logger.info(f"\n🏁 TỔNG KẾT: {t1} chủ đề giáo trình + {t2} học thuyết/nguyên tắc đã được nạp!")
