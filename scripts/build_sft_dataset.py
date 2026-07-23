#!/usr/bin/env python3
"""
scripts/build_sft_dataset.py
=============================
Chuyển đổi toàn bộ tri thức học thuật (LL.B/LL.M/Ph.D) và Kỹ năng 5 Chức danh Tư pháp từ
legal_theory_mind.db thành bộ Dữ liệu Huấn luyện AI chính thức (Supervised Fine-Tuning SFT Dataset).
Định dạng: JSONL (ChatML format) tương thích với Unsloth, HuggingFace TRL, Llama-Factory.
"""

import os
import json
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SFTBuilder")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"
OUTPUT_SFT_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_mind/legal_mind_sft_dataset.jsonl"

SYSTEM_LEGAL_MIND = (
    "Bạn là 'Lan Anh' — Chuyên gia & Trợ lý Pháp lý AI cấp cao của dự án DataLuatVN. "
    "Bạn sở hữu tư duy triết học pháp lý sâu sắc (LL.B, LL.M, Ph.D) và bộ kỹ năng thực hành chuyên sâu "
    "của 5 Chức danh Tư pháp (Luật sư, Kiểm sát viên, Thẩm phán, Chấp hành viên, Điều tra viên). "
    "Hãy đưa ra bài phân tích thấu đáo, chuẩn mực, giàu tính học thuật và bám sát thực tiễn pháp luật Việt Nam."
)

def build_sft_dataset():
    if not os.path.exists(DB_PATH):
        logger.error(f"Không tìm thấy DB tại {DB_PATH}")
        return

    os.makedirs(os.path.dirname(OUTPUT_SFT_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    sft_records = []

    # 1. Chuyển đổi Khung Tri thức Học thuật (Curriculum Topics)
    cursor.execute("SELECT degree_level, subject, topic_title, core_concept, theoretical_framework, source_university FROM curriculum_topics")
    for row in cursor.fetchall():
        degree, subject, title, concept, framework, univ = row
        user_prompt = f"Phân tích lý luận chuyên sâu về bài giảng '{title}' thuộc môn {subject} (Trình độ {degree} - {univ})?"
        assistant_reply = (
            f"📌 **Vấn đề Pháp lý Trọng tâm**: {concept}\n\n"
            f"⚖️ **Khung Lý luận & Phân tích Học thuật ({degree} - {univ})**:\n{framework}\n\n"
            f"> 💡 **Kết luận & Vận dụng**: Nội dung này đóng vai trò nền tảng trong việc định hình tư duy pháp lý, "
            f"giúp làm rõ bản chất của các chế định pháp luật liên quan."
        )
        sft_records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_LEGAL_MIND},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_reply}
            ],
            "metadata": {"type": "curriculum", "degree": degree, "subject": subject}
        })

    # 2. Chuyển đổi Học thuyết Pháp lý (Legal Doctrines)
    cursor.execute("SELECT doctrine_name, category, definition, origin_and_evolution, jurisprudence_stance, counter_arguments, related_articles FROM legal_doctrines")
    for row in cursor.fetchall():
        name, cat, dfn, origin, stance, counter, articles = row
        user_prompt = f"Phân tích bản chất, nguồn gốc và sự áp dụng của '{name}' trong Pháp luật Việt Nam?"
        assistant_reply = (
            f"⚖️ **Học thuyết / Nguyên lý**: {name} (Chuyên ngành: {cat})\n\n"
            f"📖 **Định nghĩa & Bản chất**: {dfn}\n\n"
            f"📜 **Quan điểm Pháp lý học Việt Nam**: {stance}\n\n"
            f"🔍 **Lịch sử & Sự phát triển**: {origin or 'N/A'}\n\n"
            f"📜 **Căn cứ Pháp lý Liên quan**: {articles or 'N/A'}"
        )
        sft_records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_LEGAL_MIND},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_reply}
            ],
            "metadata": {"type": "doctrine", "name": name}
        })

    # 3. Chuyển đổi Kỹ năng Thực hành 5 Chức danh Tư pháp (Legal Practice Skills)
    cursor.execute("SELECT role_name, skill_category, skill_title, procedural_stage, practical_guidelines, legal_basis, source_academy FROM legal_practice_skills")
    for row in cursor.fetchall():
        role, category, title, stage, guide, basis, academy = row
        user_prompt = f"Dưới góc độ {role}, hãy hướng dẫn quy trình nghiệp vụ thực hành '{title}' (Giai đoạn {stage})?"
        assistant_reply = (
            f"🎭 **Vai trò Chức danh Tư pháp**: {role} ({academy})\n"
            f"🛠️ **Kỹ năng Thao tác Nghiệp vụ**: {title}\n"
            f"📋 **Giai đoạn Tố tụng**: {stage}\n\n"
            f"💼 **Quy trình Hướng dẫn Thực hành Chuyên sâu**:\n{guide}\n\n"
            f"📜 **Căn cứ Pháp lý Quy định**: {basis or 'N/A'}"
        )
        sft_records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_LEGAL_MIND},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_reply}
            ],
            "metadata": {"type": "practice_skill", "role": role, "title": title}
        })

    # 4. Chuyển đổi Luận án Tiến sĩ Luật & Công trình Viện sĩ (Academic Publications)
    cursor.execute("SELECT publication_type, title, author, institution, year, abstract_summary, theoretical_contributions, keywords FROM academic_publications")
    for row in cursor.fetchall():
        p_type, title, author, inst, year, summary, contrib, kw = row
        user_prompt = f"Trình bày kết quả nghiên cứu toàn văn và đột phá lý luận của {p_type} '{title}' ({inst}, {year})?"
        assistant_reply = (
            f"🎓 **{p_type}**: {title}\n"
            f"👤 **Tác giả / Nghiên cứu sinh**: {author} ({inst}, {year})\n"
            f"🔑 **Từ khóa**: {kw}\n\n"
            f"📖 **Tóm tắt Nội dung Nghiên cứu Toàn văn**:\n{summary}\n\n"
            f"💡 **Đóng góp Đột phá Lý luận & Giá trị Học thuật**:\n{contrib}"
        )
        sft_records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_LEGAL_MIND},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_reply}
            ],
            "metadata": {"type": "dissertation", "title": title, "institution": inst}
        })

    # Ghi ra tệp JSONL
    with open(OUTPUT_SFT_PATH, "w", encoding="utf-8") as f:
        for rec in sft_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"🎉 Đã xuất thành công {len(sft_records)} mẫu SFT Data thực tế ra {OUTPUT_SFT_PATH}")
    conn.close()

if __name__ == "__main__":
    build_sft_dataset()
