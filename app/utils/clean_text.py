import re

def strip_thinking_tags(text: str) -> str:
    """Loại bỏ <think>...</think> blocks từ output của Gemma/reasoning models."""
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()


def clean_context_artifacts(text: str) -> str:
    """Loại bỏ các từ khóa kỹ thuật thô cứng, câu chúc thừa và dọn dẹp khoảng cách dòng."""
    if not text:
        return ""
    
    # 1. Loại bỏ hoàn toàn khối "Lời chúc từ Lan Anh" nếu còn xuất hiện
    text = re.sub(r'(?:💖|\*\*)*\s*Lời chúc từ Lan Anh[\s\S]*?(?=\n\s*(?:⚠️|\*\*Lưu ý|💬|👉)|$)', '', text, flags=re.IGNORECASE)

    # 2. Các thẻ tiêu đề dạng [NGỮ CẢNH ...] hoặc [TÀI LIỆU ...]
    text = re.sub(r'\[\s*(?:NGỮ CẢNH PHÁP LÝ|NGỮ CẢNH PHÁP LÝ BỔ SUNG|TÀI LIỆU PHÁP LUẬT BỔ SUNG|TÀI LIỆU PHÁP LUẬT)\s*\]', '', text, flags=re.IGNORECASE)
    
    # 3. Câu dẫn thô độc lập đầu dòng dạng "Dựa trên ngữ cảnh...", "Theo tài liệu được cung cấp..."
    text = re.sub(
        r'^\s*(?:dựa trên|dựa vào|theo|căn cứ vào)\s+(?:ngữ cảnh pháp lý|ngữ cảnh|tài liệu pháp luật|tài liệu|context)(?:\s+(?:được cung cấp|dưới đây|trên|này|chi tiết|bổ sung))*,?\s*',
        '', text, flags=re.IGNORECASE | re.MULTILINE
    )
    
    # 4. Loại bỏ tàn dư của thẻ placeholder [SEARCH: ...] nếu còn sót lại
    text = re.sub(r'\[SEARCH:\s*.*?\]', '', text, flags=re.IGNORECASE)
    
    # 5. Loại bỏ các dòng tiêu đề kịch bản thô bị in nhầm từ System Prompt
    text = re.sub(r'(?:🌸|📌|⚖️|🔍|💡|🛠️|💖|⚠️)\s*\[?\s*(?:Lời chào|Vấn đề pháp lý|Cơ sở pháp lý|Phân tích chi tiết|Kết luận|Khuyến nghị|Lời chúc|Lưu ý|Lưu ý nhỏ).*?\]?\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(?:Vì người dùng|Cần đảm bảo|Viết bằng giọng|Cấu trúc phản hồi|Trả lời:).*?\n', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 6. Loại bỏ suy nghĩ nội bộ (internal thinking preamble) trước icon chào mừng 🌸 của Lan Anh
    if "🌸" in text and not text.strip().startswith("🌸"):
        text = "🌸" + text.split("🌸", 1)[1]
    
    # 7. Dọn dẹp nhiều dòng trống liên tiếp (chỉ giữ tối đa 1 dòng trống \n\n)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Sửa hoa đầu câu nếu ký tự đầu bị chuyển thành chữ thường hoặc bị cắt mất từ đầu tiên
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def clean_document_html(html: str) -> str:
    """
    Làm sạch nội dung HTML của văn bản pháp luật:
    - Loại bỏ hoàn toàn các thông báo đăng nhập / yêu cầu tài khoản (paywall prompts).
    - Loại bỏ logo, đóng dấu bản quyền (watermark), và link trang web nguồn (LuatVietnam, Thư viện pháp luật, VBPL...).
    - Loại bỏ các thông báo tải về / hướng dẫn cài phần mềm DOC, PDF.
    - Loại bỏ các dòng lặp lại 'Tình trạng hiệu lực: Đã biết' hoặc 'Hiệu lực: Đã biết'.
    """
    if not html:
        return ""

    # 1. Loại bỏ các khối div/p chứa thông báo đăng nhập, tiện ích thành viên, ghi chú tải về
    html = re.sub(
        r'<div[^>]*>\s*<p[^>]*>\s*(?:<b>|<strong>)?\s*\**\s*Bạn chưa Đăng nhập thành viên[\s\S]*?</div>\s*</div>',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'<div[^>]*class="[^"]*(?:note-download|member-note|login-prompt)[^"]*"[^>]*>[\s\S]*?</div>',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'<p[^>]*>[\s\S]*?(?:Bạn chưa Đăng nhập thành viên|tiện ích dành cho tài khoản|Vui lòng Đăng nhập để xem chi tiết|vui lòng.*Đăng ký.*tại đây|Để đọc được văn bản tải trên)[\s\S]*?</p>',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'<div[^>]*>[\s\S]*?(?:Bạn chưa Đăng nhập thành viên|tiện ích dành cho tài khoản|Vui lòng Đăng nhập để xem chi tiết|vui lòng.*Đăng ký.*tại đây|Để đọc được văn bản tải trên)[\s\S]*?</div>',
        '', html, flags=re.IGNORECASE
    )

    # 2. Loại bỏ đóng dấu bản quyền "*** LuatVietnam.vn ***" hoặc "*** Thư viện pháp luật ***"
    html = re.sub(
        r'<[^>]*>[\s\S]*?\*{3,}\s*(?:LuatVietnam\.vn|LuatVietnam|Thư viện pháp luật|thuvienphapluat\.vn|vbpl\.vn)?\s*\*{3,}[\s\S]*?</[^>]+>',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'\*{3,}\s*(?:LuatVietnam\.vn|LuatVietnam|Thư viện pháp luật|thuvienphapluat\.vn|vbpl\.vn)\s*\*{3,}',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'(?:LuatVietnam\.vn|LuatVietnam|thuvienphapluat\.vn|thuvienphapluat|vbpl\.vn)',
        '', html, flags=re.IGNORECASE
    )

    # 3. Loại bỏ các thẻ link <a> trỏ đến trang nguồn nhưng giữ lại text bên trong (nếu không phải là link rác)
    def _replace_source_link(match):
        inner = match.group(1)
        if any(w in inner.lower() for w in ['luatvietnam', 'thuvienphapluat', 'vbpl.vn', 'đăng ký', 'đăng nhập']):
            return ''
        return inner

    html = re.sub(
        r'<a[^>]*href="[^"]*(?:luatvietnam|thuvienphapluat|vbpl\.vn)[^"]*"[^>]*>([\s\S]*?)</a>',
        _replace_source_link, html, flags=re.IGNORECASE
    )

    # 4. Loại bỏ dòng rác Tình trạng hiệu lực lặp lại trong nội dung
    html = re.sub(
        r'<p[^>]*>\s*(?:<b>|<strong>)?\s*(?:Tình trạng hiệu lực|Hiệu lực)\s*:\s*(?:Đã biết|Còn hiệu lực|Hết hiệu lực|Chưa có hiệu lực)[\s\S]*?</p>',
        '', html, flags=re.IGNORECASE
    )
    html = re.sub(
        r'(?:Tình trạng hiệu lực|Hiệu lực)\s*:\s*(?:Đã biết|Còn hiệu lực|Hết hiệu lực|Chưa có hiệu lực)',
        '', html, flags=re.IGNORECASE
    )

    # 5. Dọn dẹp thẻ trống hoặc nhiều dòng trống
    html = re.sub(r'<p[^>]*>\s*(?:&nbsp;|\s)*</p>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


def clean_document_text(text: str) -> str:
    """
    Làm sạch nội dung dạng văn bản thuần (plain text) của văn bản pháp luật:
    - Loại bỏ thông báo đăng nhập, yêu cầu tài khoản.
    - Loại bỏ đóng dấu bản quyền, logo web nguồn.
    """
    if not text:
        return ""

    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        l_lower = line.lower()
        if any(kw in l_lower for kw in [
            'bạn chưa đăng nhập thành viên',
            'tiện ích dành cho tài khoản',
            'vui lòng đăng nhập để xem chi tiết',
            'vui lòng đăng ký tại đây',
            'để đọc được văn bản tải trên',
            'luatvietnam.vn',
            'luatvietnam',
            'thuvienphapluat.vn',
            '*** luatvietnam',
            'tình trạng hiệu lực: đã biết',
            'hiệu lực: đã biết',
        ]):
            continue
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines)
    cleaned = re.sub(r'\*{3,}\s*(?:LuatVietnam|Thư viện pháp luật)?\s*\*{3,}', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

