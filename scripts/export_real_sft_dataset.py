#!/usr/bin/env python3
"""
scripts/export_real_sft_dataset.py
====================================
Script Xuất Tập Dữ liệu SFT (Instruction Tuning) THẬT 100%
từ BẢN ÁN TAND, ĐIỀU PHÁP ĐIỂN và VĂN BẢN QPPL THẬT.

Đầu ra: data/legal_mind/legal_mind_sft_dataset.jsonl
Format: ChatML (system, user, assistant)
"""

import os
import json
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ExportRealSFT")

SOURCE_MAIN_DB = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/vietnamese_legal_documents.db"
THEORY_DB = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"
OUTPUT_SFT_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_mind/legal_mind_sft_dataset.jsonl"

SYSTEM_LAN_ANH = (
    'Bạn là "Lan Anh" — Trợ lý Pháp lý Thông minh, Ấm áp, Duyên dáng và Sắc bén.\n'
    'Bạn sở hữu khả năng thấu cảm tâm lý sâu sắc, diễn đạt thuật ngữ pháp lý phức tạp bằng ngôn ngữ bình dân, tự nhiên, hợp tình hợp lý và phục vụ người dùng chu đáo nhất.'
)

def generate_real_sft():
    logger.info("=" * 70)
    logger.info("📦 BẮT ĐẦU XUẤT SFT DATASET THẬT 100% TỪ DATABASE DỰ ÁN")
    logger.info("=" * 70)

    os.makedirs(os.path.dirname(OUTPUT_SFT_PATH), exist_ok=True)
    records = []

    # 1. TRÍCH XUẤT TỪ ÁN LỆ & BẢN ÁN THẬT (1,963 Án lệ)
    if os.path.exists(THEORY_DB):
        conn = sqlite3.connect(THEORY_DB)
        c = conn.cursor()
        c.execute("""
        SELECT doc_name, precedent_number, case_type, court_level, issuing_authority, year, principle_text, full_text, applied_article_code
        FROM real_precedents
        LIMIT 2000
        """)
        rows = c.fetchall()
        for r in rows:
            doc_name, prec_num, case_type, court_lvl, authority, year, principle, full_text, applied = r
            
            user_prompt = f"Phân tích nhận định pháp lý và đường lối giải quyết trong bản án/án lệ '{doc_name}' ({prec_num or 'Bản án TAND'}) thuộc lĩnh vực {case_type or 'Dân sự'}?"
            
            assistant_resp = (
                f"🌸 Dạ Lan Anh chào bạn nha!\n\n"
                f"Về bản án/án lệ **{doc_name}** ({prec_num or 'Bản án TAND'}) do **{authority or court_lvl or 'Tòa án Nhân dân'}** ban hành năm {year or 'nhiều năm'}:\n\n"
                f"📌 **Trọng tâm đường lối giải quyết của Tòa án**:\n"
                f"{principle or full_text[:800]}\n\n"
                f"⚖️ **Căn cứ điều luật áp dụng**: {applied or 'Theo quy định Bộ luật tố tụng và luật chuyên ngành'}.\n\n"
                f"🔍 **Phân tích chi tiết nội dung bản án**:\n"
                f"{full_text[:1200]}\n\n"
                f"> 💡 **KẾT LUẬN TỪ LAN ANH:**\n"
                f"> Bản án này đặt ra tiền lệ và nguyên tắc xét xử quan trọng. Nếu bạn cần tư vấn vận dụng vào vụ việc thực tế cụ thể, Lan Anh luôn sẵn sàng hỗ trợ bạn nhé! 💖"
            )
            
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_LAN_ANH},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": assistant_resp}
                ]
            })
        conn.close()
        logger.info(f"  ✅ Đã xuất {len(records)} mẫu SFT từ Án lệ & Bản án THẬT")

    # 2. TRÍCH XUẤT TỪ ĐIỀU PHÁP ĐIỂN THẬT (2,000 Điều tiêu biểu)
    if os.path.exists(THEORY_DB):
        conn = sqlite3.connect(THEORY_DB)
        c = conn.cursor()
        c.execute("""
        SELECT article_title, chapter_title, subject_title, topic_title, content_text
        FROM real_phapdien_articles
        LIMIT 2000
        """)
        rows = c.fetchall()
        for r in rows:
            a_title, c_title, s_title, t_title, content = r
            
            user_prompt = f"Quy định pháp luật tại '{a_title}' ({c_title}) thuộc chủ đề {subject_title if 'subject_title' in locals() else s_title} quy định cụ thể như thế nào?"
            
            assistant_resp = (
                f"🌸 Dạ Lan Anh chào bạn nha!\n\n"
                f"Về quy định tại **{a_title}** thuộc **{c_title}** (Chủ đề: *{s_title} - {t_title}*):\n\n"
                f"📜 **Nội dung điều luật quy định như sau**:\n"
                f"{content}\n\n"
                f"> 💡 **TÓM TẮT NHANH TỪ LAN ANH:**\n"
                f"> Quy định trên xác định rõ quyền, nghĩa vụ và chế tài áp dụng. Bạn nhớ lưu ý thực hiện đúng trình tự pháp luật nhé!"
            )
            
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_LAN_ANH},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": assistant_resp}
                ]
            })
        conn.close()
        logger.info(f"  ✅ Đã xuất tổng cộng {len(records)} mẫu SFT bao gồm Điều Pháp điển THẬT")

    # 3. TRÍCH XUẤT TỪ VĂN BẢN QPPL THẬT (documents table - 1,000 văn bản tiêu biểu)
    if os.path.exists(SOURCE_MAIN_DB):
        conn = sqlite3.connect(SOURCE_MAIN_DB)
        c = conn.cursor()
        c.execute("""
        SELECT title, so_ky_hieu, loai_van_ban, co_quan_ban_hanh, ngay_ban_hanh, tinh_trang_hieu_luc, content_html
        FROM documents
        WHERE content_html IS NOT NULL AND length(content_html) > 200
        LIMIT 1000
        """)
        rows = c.fetchall()
        for r in rows:
            title, so_kh, loai_vb, co_quan, ngay_bh, tinh_trang, html = r
            
            # Clean HTML to text
            import re
            text_content = re.sub(r'<[^>]+>', ' ', html)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            user_prompt = f"Cho tôi biết thông tin hiệu lực và nội dung chính của {loai_vb or 'Văn bản'} số {so_kh or ''} '{title}' do {co_quan or 'cơ quan nhà nước'} ban hành?"
            
            assistant_resp = (
                f"🌸 Dạ Lan Anh chào bạn nha!\n\n"
                f"Về văn bản **{title}** (Số hiệu: `{so_kh or 'N/A'}`):\n\n"
                f"📌 **Thông tin chung**:\n"
                f"- **Loại văn bản**: {loai_vb or 'QPPL'}\n"
                f"- **Cơ quan ban hành**: {co_quan or 'Chính quyền'}\n"
                f"- **Ngày ban hành**: {ngay_bh or 'N/A'}\n"
                f"- **Trạng thái hiệu lực**: {tinh_trang or 'Đang áp dụng'}\n\n"
                f"📜 **Tóm tắt nội dung quy định**:\n"
                f"{text_content[:1000]}...\n\n"
                f"> 💡 **KHUYÊN NGHỊ TỪ LAN ANH:**\n"
                f"> Khi áp dụng văn bản này, bạn cần đối chiếu các văn bản hướng dẫn chi tiết đi kèm nhé!"
            )
            
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_LAN_ANH},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": assistant_resp}
                ]
            })
        conn.close()
        logger.info(f"  ✅ Đã xuất tổng cộng {len(records)} mẫu SFT bao gồm Văn bản QPPL THẬT")

    # GHI RA FILE JSONL
    with open(OUTPUT_SFT_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    size_mb = os.path.getsize(OUTPUT_SFT_PATH) / 1024 / 1024
    logger.info("=" * 70)
    logger.info(f"🎉 HOÀN THÀNH: Đã xuất {len(records):,} mẫu SFT THẬT 100%!")
    logger.info(f"  💾 Tệp lưu tại: {OUTPUT_SFT_PATH}")
    logger.info(f"  📦 Dung lượng tệp: {size_mb:.2f} MB")
    logger.info("=" * 70)

if __name__ == "__main__":
    generate_real_sft()
