#!/usr/bin/env python3
"""
app/utils/persona_switcher.py
==============================
Hệ thống Chuyển đổi Vai trò Chức danh Tư pháp (Judicial Persona Switcher).
Hỗ trợ 5 Chức danh Tư pháp Việt Nam:
1. Luật sư (Lawyer / Attorney)
2. Kiểm sát viên (Prosecutor)
3. Thẩm phán (Judge)
4. Chấp hành viên (Civil Enforcement Officer)
5. Điều tra viên (Criminal Investigator)
"""

import re
from typing import Dict, Any, Tuple, Optional

JUDICIAL_ROLES = {
    "lawyer": {
        "title": "Luật sư Bào chữa & Tư vấn",
        "icon": "👨‍⚖️",
        "keywords": ["luật sư", "lawyer", "attorney", "bào chữa", "thân chủ", "bảo vệ quyền lợi"],
        "prompt_style": (
            "Bạn đang đóng vai trò một LUẬT SƯ CHUYÊN NGHIỆP. Hãy tư vấn với tư duy chiến lược bảo vệ quyền "
            "và lợi ích hợp pháp tối đa cho thân chủ. Tập trung phân tích các tình tiết có lợi, tình tiết giảm nhẹ "
            "trách nhiệm hình sự/dân sự, sơ hở tố tụng của đối phương, hướng dẫn xây dựng luận cứ bào chữa/bản bảo vệ "
            "và phòng ngừa rủi ro pháp lý."
        )
    },
    "prosecutor": {
        "title": "Kiểm sát viên (Thực hành Quyền Công tố)",
        "icon": "⚖️",
        "keywords": ["kiểm sát viên", "prosecutor", "công tố", "viện kiểm sát", "vks", "truy tố", "cáo trạng"],
        "prompt_style": (
            "Bạn đang đóng vai trò một KIỂM SÁT VIÊN thực hành quyền công tố và kiểm sát hoạt động tư pháp. "
            "Hãy phân tích vụ việc dưới góc độ bảo vệ pháp chế XHCN, chống bỏ sót tội phạm và không làm oan người vô tội. "
            "Tập trung đánh giá tính hợp pháp và giá trị chứng cứ buộc tội, căn cứ phê chuẩn các lệnh cưỡng chế tố tụng, "
            "kỹ năng lập Cáo trạng và Luận tội tại phiên tòa."
        )
    },
    "judge": {
        "title": "Thẩm phán (Chủ tọa Phiên tòa)",
        "icon": "🏛️",
        "keywords": ["thẩm phán", "judge", "tòa án", "chủ tọa", "xét xử", "tuyên án", "án lệ", "bản án"],
        "prompt_style": (
            "Bạn đang đóng vai trò một THẨM PHÁN CHỦ TỌA PHIÊN TÒA. Hãy phân tích vụ việc với thái độ khách quan, "
            "công tâm, vô tư tuyệt đối. Tập trung đánh giá tính tương đồng tình tiết thực tế với các Án lệ hiện hành, "
            "cân nhắc bình đẳng chứng cứ các bên (VKS, Luật sư, Đương sự), điều hành tranh tụng công khai và hướng dẫn "
            "soạn thảo Bản án thấu tình đạt lý."
        )
    },
    "enforcement": {
        "title": "Chấp hành viên Thi hành án",
        "icon": "👮‍♂️",
        "keywords": ["chấp hành viên", "thi hành án", "enforcement", "kê biên", "phong tỏa", "đấu giá tài sản"],
        "prompt_style": (
            "Bạn đang đóng vai trò một CHẤP HÀNH VIÊN THI HÀNH ÁN DÂN SỰ. Hãy phân tích vụ việc dưới góc độ bảo đảm "
            "tính hiệu lực của Bản án/Quyết định Tòa án. Tập trung vào nghiệp vụ xác minh điều kiện thi hành án, "
            "biện pháp cưỡng chế kê biên tài sản, phong tỏa tài khoản ngân hàng, quy định định giá và bán đấu giá tài sản."
        )
    },
    "investigator": {
        "title": "Điều tra viên Hình sự",
        "icon": "🕵️‍♂️",
        "keywords": ["điều tra viên", "investigator", "cơ quan điều tra", "cqđt", "khám nghiệm", "hỏi cung"],
        "prompt_style": (
            "Bạn đang đóng vai trò một ĐIỀU TRA VIÊN HÌNH SỰ. Hãy phân tích vụ việc với tư duy khoa học hình sự "
            "khách quan. Tập trung vào kỹ năng tiếp nhận giải quyết tố giác tin báo tội phạm, nghiệp vụ khám nghiệm "
            "hiện trường, phương pháp hỏi cung bị can, thu thập bảo quản dấu vết vật chứng và lập Kết luận điều tra."
        )
    }
}

def detect_persona_switch(prompt: str) -> Tuple[Optional[str], str]:
    """
    Phát hiện câu lệnh hoặc từ khóa chuyển đổi vai trò trong câu hỏi.
    Trả về: (role_key, cleaned_prompt)
    """
    if not prompt:
        return None, prompt

    # 1. Phát hiện câu lệnh /role <role_name>
    cmd_match = re.match(r'^\/role\s+(\w+)', prompt.strip(), re.IGNORECASE)
    if cmd_match:
        role_arg = cmd_match.group(1).lower()
        cleaned = prompt[cmd_match.end():].strip()
        for key, role_data in JUDICIAL_ROLES.items():
            if role_arg in [key, role_data["title"].lower()] or role_arg in [kw.lower() for kw in role_data["keywords"]]:
                return key, cleaned
        if role_arg in ["reset", "off", "default", "normal"]:
            return "default", cleaned

    # 2. Phát hiện từ khóa ngữ cảnh tự nhiên
    lower_p = prompt.lower()
    for key, role_data in JUDICIAL_ROLES.items():
        for kw in role_data["keywords"]:
            pattern = r'\b(dưới góc độ|với tư cách|đóng vai|vai trò|nhìn từ|là)\s+' + re.escape(kw)
            if re.search(pattern, lower_p):
                return key, prompt

    return None, prompt

def get_persona_system_prompt(role_key: Optional[str], include_skills: bool = True) -> str:
    """
    Trả về System Prompt chuyên biệt cho Vai trò Chức danh Tư pháp.
    
    Nâng cấp: Tự động truy xuất kỹ năng nghiệp vụ từ DB legal_theory_mind.db
    để bổ sung chi tiết nghiệp vụ thực tế cho mỗi vai trò.
    """
    if not role_key or role_key not in JUDICIAL_ROLES:
        return ""

    role_info = JUDICIAL_ROLES[role_key]
    
    # Base prompt
    prompt = (
        f"\n\n🎭 **CHẾ ĐỘ VAI TRÒ CHỨC DANH TƯ PHÁP CHUYÊN SÂU**: {role_info['icon']} {role_info['title']}\n"
        f"{role_info['prompt_style']}\n"
    )
    
    # Fetch practice skills from DB (if available)
    if include_skills:
        try:
            skills_context = _fetch_role_skills(role_info["title"])
            if skills_context:
                prompt += f"\n{skills_context}\n"
        except Exception as e:
            import logging
            logging.getLogger("PersonaSwitcher").warning(f"Could not load skills: {e}")
    
    prompt += f"\nHãy trình bày câu trả lời thể hiện rõ nét tư duy nghiệp vụ và phong thái chuẩn mực của {role_info['title']}."
    
    return prompt


def _fetch_role_skills(role_name: str, max_skills: int = 4) -> str:
    """
    Truy xuất kỹ năng nghiệp vụ từ bảng legal_practice_skills cho một vai trò cụ thể.
    Trả về context string ngắn gọn để inject vào system prompt.
    """
    import os
    import sqlite3
    
    db_path = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"
    if not os.path.exists(db_path):
        return ""
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Map back to simple role name for DB
        db_roles = {
            "Luật sư Bào chữa & Tư vấn": "Luật sư",
            "Kiểm sát viên (Thực hành Quyền Công tố)": "Kiểm sát viên",
            "Thẩm phán (Chủ tọa Phiên tòa)": "Thẩm phán",
            "Chấp hành viên Thi hành án": "Chấp hành viên",
            "Điều tra viên Hình sự": "Điều tra viên"
        }
        db_role_name = db_roles.get(role_name, role_name)
        
        c.execute("""
        SELECT skill_title, procedural_stage, practical_guidelines, legal_basis
        FROM legal_practice_skills
        WHERE role_name = ?
        ORDER BY id
        LIMIT ?
        """, (db_role_name, max_skills))
        
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return ""
        
        parts = [f"\n### 📋 Kỹ năng Nghiệp vụ {role_name}:\n"]
        for i, (title, stage, guidelines, basis) in enumerate(rows, 1):
            summary = guidelines[:500] + "..." if len(guidelines) > 500 else guidelines
            parts.append(f"**{i}. {title}** (Giai đoạn: {stage})")
            parts.append(f"   Căn cứ: {basis}")
            parts.append(f"   {summary}\n")
        
        return "\n".join(parts)
    
    except Exception:
        return ""


def get_all_roles_summary() -> str:
    """Trả về bảng tóm tắt 5 vai trò tư pháp (cho /role help)."""
    lines = ["🎭 **5 Vai trò Chức danh Tư pháp khả dụng:**\n"]
    for key, info in JUDICIAL_ROLES.items():
        lines.append(f"  {info['icon']} `/role {key}` — {info['title']}")
    lines.append(f"\n  🔄 `/role reset` — Quay lại chế độ bình thường")
    return "\n".join(lines)


if __name__ == "__main__":
    test_p1 = "/role lawyer Tư vấn cho anh thủ tục kiện bồi thường hợp đồng"
    r1, p1 = detect_persona_switch(test_p1)
    print(f"Role: {r1} | Prompt: {p1}")
    print(get_persona_system_prompt(r1))
    print("\n" + "="*60 + "\n")
    print(get_all_roles_summary())

