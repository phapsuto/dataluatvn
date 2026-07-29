import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.file_parsers import parse_file
from app.utils.legal_doc_analyzer import AttachmentSessionManager, LegalDocumentAnalyzer
from app.routers.chatbot import _enrich_prompt_with_attachment

def test_parse_file_txt():
    content = "Hợp đồng lao động số 01/2026/HĐLĐ. Bên A: Công ty Vincode. Bên B: Nguyễn Văn A."
    res = parse_file("hop_dong.txt", content.encode("utf-8"))
    assert "Hợp đồng lao động số 01/2026/HĐLĐ" in res
    assert "Bên A: Công ty Vincode" in res

def test_parse_file_csv():
    csv_data = "STT,Họ tên,Nghĩa vụ\n1,Nguyễn Văn A,Bảo mật thông tin\n2,Trần Thị B,Bồi thường vi phạm"
    res = parse_file("danh_sach.csv", csv_data.encode("utf-8"))
    assert "Nguyễn Văn A" in res
    assert "Bảo mật thông tin" in res

def test_attachment_session_manager_crud():
    session_id = "test_user_session_1"
    
    # Save first attachment
    att1 = AttachmentSessionManager.save_attachment(
        session_id=session_id,
        filename="hop_dong_lao_dong.docx",
        file_type="DOCX",
        content_text="Nội dung hợp đồng thử việc...",
        structured_summary="Tóm tắt hợp đồng lao động giữa bên A và B...",
        doc_type="Hợp đồng lao động"
    )
    assert att1["attachment_id"].startswith("att_")
    assert att1["filename"] == "hop_dong_lao_dong.docx"
    
    # Retrieve by ID
    fetched = AttachmentSessionManager.get_attachment(att1["attachment_id"])
    assert fetched is not None
    assert fetched["doc_type"] == "Hợp đồng lao động"
    
    # Retrieve session list
    list_atts = AttachmentSessionManager.get_session_attachments(session_id)
    assert len(list_atts) >= 1

    # Delete attachment
    deleted = AttachmentSessionManager.delete_attachment(att1["attachment_id"])
    assert deleted is True
    assert AttachmentSessionManager.get_attachment(att1["attachment_id"]) is None

import time
def test_attachment_session_max_10_files_limit():
    session_id = f"test_limit_session_{time.time()}"
    # Try adding 11 files
    for i in range(10):
        AttachmentSessionManager.save_attachment(
            session_id=session_id,
            filename=f"file_{i}.txt",
            file_type="TXT",
            content_text=f"Nội dung file {i}",
            structured_summary=f"Summary {i}",
            doc_type="Văn bản pháp lý"
        )
    
    with pytest.raises(ValueError) as excinfo:
        AttachmentSessionManager.save_attachment(
            session_id=session_id,
            filename="file_11.txt",
            file_type="TXT",
            content_text="Nội dung vượt quá giới hạn",
            structured_summary="Summary 11",
            doc_type="Văn bản pháp lý"
        )
    assert "Mỗi phiên hội thoại chỉ được tải lên tối đa 10 tài liệu" in str(excinfo.value)

def test_enrich_prompt_with_attachment():
    # Save a mock attachment
    att = AttachmentSessionManager.save_attachment(
        session_id="test_enrich_session",
        filename="quyet_dinh_01.txt",
        file_type="TXT",
        content_text="Quyết định xử phạt vi phạm hành chính số 123/QĐ-XPHC.",
        structured_summary="Quyết định xử phạt đối với công ty X về hành vi vi phạm môi trường.",
        doc_type="Quyết định hành chính"
    )
    
    prompt = "Quyết định này có hợp pháp không?"
    enriched = _enrich_prompt_with_attachment(prompt, att["attachment_id"], None)
    
    assert "Quyết định này có hợp pháp không?" in enriched
    assert "quyet_dinh_01.txt" in enriched
    assert "Quyết định xử phạt đối với công ty X" in enriched
    assert "YÊU CẦU ĐỐI CHIẾU PHÁP LÝ VIỆT NAM" in enriched

def test_enrich_prompt_with_session_id():
    session_id = f"test_session_enrich_{time.time()}"
    AttachmentSessionManager.save_attachment(
        session_id=session_id,
        filename="hop_dong_dich_vu.docx",
        file_type="DOCX",
        content_text="Hợp đồng dịch vụ phần mềm trị giá 500 triệu đồng.",
        structured_summary="Tóm tắt hợp đồng dịch vụ...",
        doc_type="Hợp đồng kinh tế"
    )
    prompt = "Kiểm tra rủi ro trong tài liệu"
    enriched = _enrich_prompt_with_attachment(prompt, None, None, session_id=session_id)
    assert "Kiểm tra rủi ro trong tài liệu" in enriched
    assert "hop_dong_dich_vu.docx" in enriched
    assert "NGỮ CẢNH CÁC TÀI LIỆU ĐÍNH KÈM TRONG PHIÊN" in enriched

def test_clear_session_attachments():
    session_id = f"test_clear_session_{time.time()}"
    for i in range(3):
        AttachmentSessionManager.save_attachment(
            session_id=session_id,
            filename=f"doc_{i}.txt",
            file_type="TXT",
            content_text=f"Content {i}",
            structured_summary=f"Summary {i}",
            doc_type="TXT"
        )
    assert len(AttachmentSessionManager.get_session_attachments(session_id)) == 3
    cleared_count = AttachmentSessionManager.clear_session(session_id)
    assert cleared_count == 3
    assert len(AttachmentSessionManager.get_session_attachments(session_id)) == 0

if __name__ == "__main__":
    test_parse_file_txt()
    test_parse_file_csv()
    test_attachment_session_manager_crud()
    test_attachment_session_max_10_files_limit()
    test_enrich_prompt_with_attachment()
    test_enrich_prompt_with_session_id()
    test_clear_session_attachments()
    print("All Multimodal Legal Upload & RAG tests passed successfully!")
