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


from bs4 import BeautifulSoup

def clean_document_html(html: str) -> str:
    """
    Làm sạch nội dung HTML của văn bản pháp luật bằng BeautifulSoup + regex:
    - Loại bỏ hoàn toàn các khung dấu đỏ độc quyền, SVG logo LuatVietnam / Thư viện pháp luật.
    - Loại bỏ các khối thông báo trạng thái rác ('Tình trạng hiệu lực: Đã biết', 'Hiệu lực: Đã biết').
    - Loại bỏ hoàn toàn các thông báo đăng nhập / yêu cầu tài khoản (paywall prompts).
    - Loại bỏ các thông báo tải về / hướng dẫn cài phần mềm DOC, PDF.
    - Gỡ bỏ link (unwrap) trỏ về các trang web nguồn (LuatVietnam, Thư viện pháp luật, VBPL).
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Loại bỏ các khối container rác từ LuatVietnam / Thư viện pháp luật
        bad_classes = [
            "fix_docquyen", "khung_docquyen", "text_docquyen", "img-bgdocquyen",
            "row-status", "item-status", "note-download", "list-download",
            "the-document-header", "tooltip-1", "btn-tip-r-more", "div-table",
            "note-login", "member-note", "login-prompt", "box-text-content"
        ]
        for bad_cls in bad_classes:
            for el in soup.find_all(class_=bad_cls):
                el.decompose()

        # 2. Loại bỏ các thẻ svg/img logo, dấu bản quyền, icon tải về
        for svg in soup.find_all("svg"):
            svg.decompose()
        for img in soup.find_all("img"):
            src = (img.get("src", "") or "") + (img.get("data-src", "") or "")
            if any(k in src.lower() for k in ["luatvietnam", "thuvienphapluat", "download-pdf", "download-docx", "logo"]):
                img.decompose()

        # 3. Gỡ liên kết (unwrap) trỏ về các website nguồn hoặc đăng nhập/đăng ký
        for a in soup.find_all("a"):
            href = (a.get("href", "") or "").lower()
            if any(k in href for k in ["luatvietnam", "thuvienphapluat", "vbpl.vn", "login", "register", "javascript:void(0)"]):
                a.unwrap()

        # 4. Loại bỏ các thẻ chứa thông báo paywall, tình trạng hiệu lực rác, đóng dấu bản quyền
        bad_keywords = [
            "bạn chưa đăng nhập thành viên",
            "tiện ích dành cho tài khoản",
            "vui lòng đăng nhập để xem",
            "vui lòng đăng ký tại đây",
            "để đọc được văn bản tải trên",
            "luatvietnam.vn",
            "luatvietnam",
            "*** luatvietnam",
            "*** thư viện pháp luật",
            "thuvienphapluat.vn",
            "tình trạng hiệu lực: đã biết",
            "tình trạng hiệu lực: còn hiệu lực",
            "tình trạng hiệu lực: chưa có hiệu lực",
            "tình trạng hiệu lực: hết hiệu lực",
            "hiệu lực: đã biết",
            "hiệu lực: còn hiệu lực",
            "hiệu lực: chưa có hiệu lực",
            "hiệu lực: hết hiệu lực",
            "ngày hết hiệu lực:",
            "ngày áp dụng:"
        ]
        for tag in list(soup.find_all(["p", "div", "span", "strong", "b", "li", "td"])):
            txt = tag.get_text().strip().lower()
            if any(kw in txt for kw in bad_keywords) and len(txt) < 300:
                tag.decompose()

        html = str(soup)
    except Exception:
        pass

    # 5. Fallback regex dọn dẹp chuỗi sót lại
    html = re.sub(r'\*{3,}\s*(?:LuatVietnam\.vn|LuatVietnam|Thư viện pháp luật|thuvienphapluat\.vn|vbpl\.vn)?\s*\*{3,}', '', html, flags=re.IGNORECASE)
    html = re.sub(r'(?:Tình trạng hiệu lực|Hiệu lực)\s*:\s*(?:Đã biết|Còn hiệu lực|Hết hiệu lực|Chưa có hiệu lực)', '', html, flags=re.IGNORECASE)
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
            '*** thư viện pháp luật',
            'tình trạng hiệu lực: đã biết',
            'tình trạng hiệu lực: còn hiệu lực',
            'tình trạng hiệu lực: chưa có hiệu lực',
            'tình trạng hiệu lực: hết hiệu lực',
            'hiệu lực: đã biết',
            'hiệu lực: còn hiệu lực',
            'hiệu lực: chưa có hiệu lực',
            'hiệu lực: hết hiệu lực',
            'ngày hết hiệu lực:',
            'ngày áp dụng:',
        ]):
            continue
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines)
    cleaned = re.sub(r'\*{3,}\s*(?:LuatVietnam|Thư viện pháp luật)?\s*\*{3,}', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

