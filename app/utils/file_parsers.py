import fitz  # PyMuPDF
from docx import Document
import io

import requests
import base64
import os

def _fpt_ocr_image_base64(base64_img: str) -> str:
    """Calls FPT Cloud Vision API to extract text from a base64 image."""
    api_key = os.environ.get("FPT_CLOUD_API_KEY") or os.environ.get("FPT_API_KEY")
    if not api_key:
        return ""
        
    url = "https://mkp-api.fptcloud.com/v1/chat/completions"
    payload = {
        "model": "Qwen2.5-VL-7B-Instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Trích xuất toàn bộ văn bản có trong hình ảnh này. Chỉ trả về văn bản được trích xuất, không giải thích gì thêm."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }
    
    try:
        res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        if res.status_code == 200:
            data = res.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            raise Exception(f"API Error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[OCR Error] {e}")
        raise e

def parse_pdf(file_bytes: bytes, progress_callback=None) -> str:
    """Extracts text from a PDF file. Uses FPT Vision OCR for scanned pages."""
    text = ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        page_results = [None] * total_pages
        tasks = []
        completed = 0
        
        for i, page in enumerate(doc):
            page_text = page.get_text().strip()
            if len(page_text) < 50:
                # Likely a scanned page, try OCR
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # 2x zoom for better OCR
                img_bytes = pix.tobytes("png")
                b64_img = base64.b64encode(img_bytes).decode("utf-8")
                tasks.append((i, b64_img))
            else:
                page_results[i] = page_text + "\n\n"
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_pages)
        
        # Run OCR concurrently
        if tasks:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_idx = {executor.submit(_fpt_ocr_image_base64, b64): idx for idx, b64 in tasks}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        ocr_text = future.result()
                        if not ocr_text.strip():
                            page_results[idx] = "\n\n[LỖI: TRANG NÀY KHÔNG NHẬN DIỆN ĐƯỢC CHỮ]\n\n"
                        else:
                            page_results[idx] = ocr_text + "\n\n"
                    except Exception as e:
                        print(f"[OCR Task Error] {e}")
                        page_results[idx] = "\n\n[LỖI: QUÁ TRÌNH OCR TRANG NÀY BỊ THẤT BẠI]\n\n"
                    
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total_pages)
                        
        text = "".join(filter(None, page_results))
    except Exception as e:
        raise ValueError(f"Lỗi khi đọc file PDF: {str(e)}")
    return text.strip()

def parse_docx(file_bytes: bytes, progress_callback=None) -> str:
    """Extracts text from a DOCX file."""
    text = ""
    try:
        doc = Document(io.BytesIO(file_bytes))
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        raise ValueError(f"Lỗi khi đọc file DOCX: {str(e)}")
    return text.strip()

def parse_txt(file_bytes: bytes, progress_callback=None) -> str:
    """Extracts text from a TXT file."""
    try:
        if progress_callback:
            progress_callback(1, 1)
        return file_bytes.decode('utf-8').strip()
    except UnicodeDecodeError:
        try:
            return file_bytes.decode('windows-1258').strip()
        except Exception:
            raise ValueError("Lỗi khi đọc file TXT: Không thể giải mã định dạng file")
    except Exception as e:
        raise ValueError(f"Lỗi khi đọc file TXT: {str(e)}")

def parse_file(filename: str, file_bytes: bytes, progress_callback=None) -> str:
    """Detects file type and extracts text."""
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.pdf'):
        return parse_pdf(file_bytes, progress_callback)
    elif filename_lower.endswith('.docx') or filename_lower.endswith('.doc'):
        # For .doc we just try docx parser, it might fail but it's the best we have without abiword/antiword
        if progress_callback:
            progress_callback(1, 1)
        return parse_docx(file_bytes, progress_callback)
    elif filename_lower.endswith('.txt') or filename_lower.endswith('.csv'):
        return parse_txt(file_bytes, progress_callback)
    else:
        raise ValueError("Định dạng file không được hỗ trợ. Chỉ hỗ trợ PDF, DOCX, TXT.")
