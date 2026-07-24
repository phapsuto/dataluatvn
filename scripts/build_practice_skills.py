#!/usr/bin/env python3
"""
scripts/build_practice_skills.py
==================================
BƯỚC 6: Sinh Kỹ năng Nghiệp vụ + Mẫu Văn bản cho 5 Vai trò Tư pháp
bằng LLM Knowledge Distillation (FPT Cloud Gemma-4-31B-it).

5 Vai trò:
1. Thẩm phán (Judge) — Xét xử, soạn Bản án, áp dụng Án lệ
2. Luật sư (Lawyer) — Bào chữa, soạn Luận cứ, Bản bảo vệ quyền lợi
3. Kiểm sát viên (Prosecutor) — Truy tố, soạn Cáo trạng, Luận tội
4. Điều tra viên (Investigator) — Điều tra, soạn Kết luận Điều tra
5. Chấp hành viên (Enforcement) — Thi hành án, soạn Quyết định THA
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv("/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/.env")

import litellm
litellm.telemetry = False
litellm.drop_params = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("PracticeSkillsBuilder")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"
FPT_API_KEY = os.environ.get("FPT_CLOUD_API_KEY", "")
FPT_MODEL = "custom_openai/gemma-4-31B-it"
FPT_API_BASE = "https://mkp-api.fptcloud.com/v1"

# ══════════════════════════════════════════════════════════════
# KỸ NĂNG NGHIỆP VỤ 5 VAI TRÒ TƯ PHÁP
# ══════════════════════════════════════════════════════════════

PRACTICE_SKILLS = {
    "Thẩm phán": {
        "role_key": "judge",
        "skills": [
            {"title": "Kỹ năng nghiên cứu hồ sơ vụ án trước khi mở phiên tòa", "stage": "Chuẩn bị xét xử", "legal_basis": "Điều 203-220 BLTTDS 2015, Điều 277-285 BLTTHS 2015"},
            {"title": "Kỹ năng đánh giá chứng cứ và xác định sự thật khách quan", "stage": "Xét xử", "legal_basis": "Điều 108 BLTTDS 2015, Điều 86-87 BLTTHS 2015"},
            {"title": "Kỹ năng điều hành phiên tòa tranh tụng công khai", "stage": "Xét xử", "legal_basis": "Điều 247-259 BLTTDS 2015, Điều 307-323 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Bản án sơ thẩm dân sự chuẩn mực", "stage": "Sau xét xử", "legal_basis": "Điều 266-270 BLTTDS 2015"},
            {"title": "Kỹ năng soạn thảo Bản án hình sự sơ thẩm", "stage": "Sau xét xử", "legal_basis": "Điều 260 BLTTHS 2015"},
            {"title": "Kỹ năng áp dụng Án lệ trong xét xử", "stage": "Xét xử", "legal_basis": "Nghị quyết 04/2019/NQ-HĐTP của HĐTP TANDTC"},
            {"title": "Kỹ năng hòa giải trong tố tụng dân sự", "stage": "Chuẩn bị xét xử", "legal_basis": "Điều 205-213 BLTTDS 2015"},
            {"title": "Kỹ năng quyết định hình phạt (cá thể hóa hình phạt)", "stage": "Xét xử", "legal_basis": "Điều 50-59 BLHS 2015"},
        ]
    },
    "Luật sư": {
        "role_key": "lawyer",
        "skills": [
            {"title": "Kỹ năng tiếp xúc và trao đổi với thân chủ", "stage": "Tiếp nhận vụ việc", "legal_basis": "Luật Luật sư 2006 sửa đổi 2012, Điều 73 BLTTHS 2015"},
            {"title": "Kỹ năng phân tích hồ sơ vụ án và xây dựng chiến lược bào chữa", "stage": "Chuẩn bị", "legal_basis": "Điều 73-74 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Luận cứ bào chữa trong vụ án hình sự", "stage": "Bào chữa", "legal_basis": "Điều 320-322 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Bản bảo vệ quyền lợi hợp pháp cho đương sự dân sự", "stage": "Bảo vệ quyền lợi", "legal_basis": "Điều 75-76 BLTTDS 2015"},
            {"title": "Kỹ năng tranh luận và phản bác chứng cứ tại phiên tòa", "stage": "Tranh tụng", "legal_basis": "Điều 322 BLTTHS 2015, Điều 260 BLTTDS 2015"},
            {"title": "Kỹ năng soạn thảo Đơn kháng cáo và Đơn khiếu nại tố tụng", "stage": "Sau xét xử", "legal_basis": "Điều 331 BLTTHS 2015, Điều 271 BLTTDS 2015"},
            {"title": "Kỹ năng tư vấn pháp lý và phòng ngừa rủi ro pháp lý cho doanh nghiệp", "stage": "Tư vấn", "legal_basis": "Luật Luật sư 2006"},
            {"title": "Kỹ năng đàm phán và thương lượng hợp đồng", "stage": "Tư vấn", "legal_basis": "BLDS 2015, Luật Thương mại 2005"},
        ]
    },
    "Kiểm sát viên": {
        "role_key": "prosecutor",
        "skills": [
            {"title": "Kỹ năng kiểm sát việc khởi tố vụ án và khởi tố bị can", "stage": "Khởi tố", "legal_basis": "Điều 161-165 BLTTHS 2015"},
            {"title": "Kỹ năng phê chuẩn lệnh bắt, tạm giam, khám xét", "stage": "Điều tra", "legal_basis": "Điều 113-117, 192-198 BLTTHS 2015"},
            {"title": "Kỹ năng đánh giá chứng cứ buộc tội và quyết định truy tố", "stage": "Truy tố", "legal_basis": "Điều 236-248 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Cáo trạng truy tố bị can ra Tòa", "stage": "Truy tố", "legal_basis": "Điều 243 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Luận tội và trình bày Luận tội tại phiên tòa", "stage": "Xét xử", "legal_basis": "Điều 321 BLTTHS 2015"},
            {"title": "Kỹ năng tranh luận với Luật sư bào chữa tại phiên tòa", "stage": "Xét xử", "legal_basis": "Điều 322 BLTTHS 2015"},
            {"title": "Kỹ năng kháng nghị bản án theo thủ tục phúc thẩm", "stage": "Sau xét xử", "legal_basis": "Điều 336-337 BLTTHS 2015"},
            {"title": "Kỹ năng kiểm sát thi hành án hình sự", "stage": "Thi hành án", "legal_basis": "Luật Thi hành án hình sự 2019"},
        ]
    },
    "Điều tra viên": {
        "role_key": "investigator",
        "skills": [
            {"title": "Kỹ năng tiếp nhận và xử lý tố giác, tin báo tội phạm", "stage": "Tiếp nhận", "legal_basis": "Điều 145-147 BLTTHS 2015"},
            {"title": "Kỹ năng khám nghiệm hiện trường vụ án hình sự", "stage": "Điều tra", "legal_basis": "Điều 201-204 BLTTHS 2015"},
            {"title": "Kỹ năng hỏi cung bị can theo đúng pháp luật", "stage": "Điều tra", "legal_basis": "Điều 183-188 BLTTHS 2015"},
            {"title": "Kỹ năng thu thập, bảo quản vật chứng và dấu vết", "stage": "Điều tra", "legal_basis": "Điều 89-90, 105-106 BLTTHS 2015"},
            {"title": "Kỹ năng lấy lời khai người bị hại, người làm chứng", "stage": "Điều tra", "legal_basis": "Điều 185-188 BLTTHS 2015"},
            {"title": "Kỹ năng trưng cầu giám định (pháp y, kỹ thuật hình sự)", "stage": "Điều tra", "legal_basis": "Điều 205-210 BLTTHS 2015"},
            {"title": "Kỹ năng soạn thảo Kết luận Điều tra vụ án hình sự", "stage": "Kết thúc điều tra", "legal_basis": "Điều 232-234 BLTTHS 2015"},
            {"title": "Kỹ năng áp dụng biện pháp ngăn chặn (bắt, tạm giữ, tạm giam)", "stage": "Điều tra", "legal_basis": "Điều 109-129 BLTTHS 2015"},
        ]
    },
    "Chấp hành viên": {
        "role_key": "enforcement",
        "skills": [
            {"title": "Kỹ năng ra Quyết định thi hành án dân sự", "stage": "Khởi động THA", "legal_basis": "Điều 36 Luật THADS 2008 sửa đổi 2014"},
            {"title": "Kỹ năng xác minh điều kiện thi hành án", "stage": "Xác minh", "legal_basis": "Điều 44 Luật THADS"},
            {"title": "Kỹ năng thương lượng, thỏa thuận thi hành án", "stage": "Tự nguyện THA", "legal_basis": "Điều 46 Luật THADS"},
            {"title": "Kỹ năng cưỡng chế kê biên tài sản để thi hành án", "stage": "Cưỡng chế", "legal_basis": "Điều 71-81 Luật THADS"},
            {"title": "Kỹ năng phong tỏa tài khoản ngân hàng và khấu trừ thu nhập", "stage": "Cưỡng chế", "legal_basis": "Điều 76-77 Luật THADS"},
            {"title": "Kỹ năng định giá và bán đấu giá tài sản thi hành án", "stage": "Xử lý tài sản", "legal_basis": "Điều 98-104 Luật THADS"},
        ]
    }
}


def call_llm(prompt: str, max_tokens: int = 1500) -> str:
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check and add missing columns
    c.execute("PRAGMA table_info(legal_practice_skills)")
    existing_cols = [r[1] for r in c.fetchall()]
    
    if "content_hash" not in existing_cols:
        c.execute("ALTER TABLE legal_practice_skills ADD COLUMN content_hash TEXT")
    if "created_at" not in existing_cols:
        c.execute("ALTER TABLE legal_practice_skills ADD COLUMN created_at TEXT")
    
    conn.commit()
    conn.close()


def build_practice_skills():
    logger.info("=" * 80)
    logger.info("🎯 BƯỚC 6: SINH KỸ NĂNG NGHIỆP VỤ 5 VAI TRÒ TƯ PHÁP")
    logger.info("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    total_saved = 0
    total_roles = len(PRACTICE_SKILLS)
    
    for role_idx, (role_name, role_info) in enumerate(PRACTICE_SKILLS.items(), 1):
        role_key = role_info["role_key"]
        skills = role_info["skills"]
        logger.info(f"\n{'='*60}")
        logger.info(f"🎭 [{role_idx}/{total_roles}] Vai trò: {role_name} ({len(skills)} kỹ năng)")
        logger.info(f"{'='*60}")
        
        for skill_idx, skill in enumerate(skills, 1):
            title = skill["title"]
            stage = skill["stage"]
            legal_basis = skill["legal_basis"]
            
            content_hash = hashlib.md5(f"{role_key}:{title}".encode()).hexdigest()
            
            c.execute("SELECT id FROM legal_practice_skills WHERE content_hash=?", (content_hash,))
            if c.fetchone():
                logger.info(f"   ⏭️ [{skill_idx}/{len(skills)}] Đã có: {title[:50]}")
                continue
            
            prompt = f"""Bạn là chuyên gia đào tạo nghiệp vụ tư pháp tại Học viện Tư pháp Việt Nam. 
Hãy viết hướng dẫn nghiệp vụ chi tiết cho kỹ năng sau:

VAI TRÒ: {role_name}
KỸ NĂNG: {title}
GIAI ĐOẠN TỐ TỤNG: {stage}
CĂN CỨ PHÁP LÝ: {legal_basis}

YÊU CẦU:
1. MÔ TẢ KỸ NĂNG (200-300 từ): Nội dung, tầm quan trọng, yêu cầu đặt ra.
2. QUY TRÌNH THỰC HIỆN (400-600 từ): Liệt kê từng bước chi tiết, lưu ý nghiệp vụ, sai lầm cần tránh.
3. MẪU VĂN BẢN (nếu có): Nêu cấu trúc/bố cục chuẩn của văn bản tố tụng liên quan (Bản án, Cáo trạng, Luận cứ Bào chữa, Kết luận Điều tra...). Viết bố cục mẫu chi tiết.

Viết bằng tiếng Việt, chuyên sâu, thực tiễn, chính xác theo pháp luật Việt Nam hiện hành."""

            result = call_llm(prompt, max_tokens=1500)
            if not result or len(result) < 200:
                logger.warning(f"   ⚠️ LLM trả về rỗng cho: {title}")
                continue
            
            try:
                c.execute("""
                INSERT OR IGNORE INTO legal_practice_skills
                (role_name, skill_category, skill_title, procedural_stage, practical_guidelines, legal_basis, source_academy, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    role_name, stage, title,
                    stage,
                    result,
                    legal_basis,
                    "Knowledge Distillation (FPT Cloud Gemma-4-31B-it)",
                    content_hash,
                    datetime.now().isoformat()
                ))
                
                if c.rowcount > 0:
                    row_id = c.lastrowid
                    fts_title = f"🎯 {role_name} | {title}"
                    c.execute("""
                    INSERT INTO fts_theory (source_table, source_id, title, content, category)
                    VALUES ('legal_practice_skills', ?, ?, ?, ?)
                    """, (row_id, fts_title, result[:15000], f"Kỹ năng {role_name}"))
                    
                    conn.commit()
                    total_saved += 1
                    word_count = len(result.split())
                    logger.info(f"   ✅ [{skill_idx}/{len(skills)}] {title[:55]} | {word_count} từ")
            except Exception as e:
                logger.error(f"   ❌ DB Error: {e}")
            
            time.sleep(1.5)
    
    conn.close()
    logger.info(f"\n{'='*80}")
    logger.info(f"🎉 HOÀN THÀNH: Đã sinh và lưu {total_saved} kỹ năng nghiệp vụ vào legal_practice_skills!")
    logger.info(f"{'='*80}")
    return total_saved


if __name__ == "__main__":
    setup_db()
    total = sum(len(role["skills"]) for role in PRACTICE_SKILLS.values())
    logger.info(f"🚀 Bắt đầu sinh {total} kỹ năng nghiệp vụ cho 5 vai trò tư pháp...")
    build_practice_skills()
