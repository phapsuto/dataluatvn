"""
Admin CRUD Schemas — Pydantic models cho Create/Update operations.
Dùng cho admin endpoints chỉnh sửa dữ liệu Luật, Án Lệ, Pháp Điển.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ╔══════════════════════════════════════════════════════════════╗
# ║                     LAWS (documents)                        ║
# ╚══════════════════════════════════════════════════════════════╝

class LawCreate(BaseModel):
    title: str = Field(..., min_length=1, description="Tiêu đề văn bản")
    so_ky_hieu: Optional[str] = Field(None, description="Số ký hiệu (vd: 01/2024/NĐ-CP)")
    ngay_ban_hanh: Optional[str] = Field(None, description="Ngày ban hành (dd/mm/yyyy)")
    loai_van_ban: Optional[str] = Field(None, description="Loại văn bản")
    co_quan_ban_hanh: Optional[str] = Field(None, description="Cơ quan ban hành")
    tinh_trang_hieu_luc: Optional[str] = Field(None, description="Tình trạng hiệu lực")
    ngay_co_hieu_luc: Optional[str] = Field(None, description="Ngày có hiệu lực")
    ngay_het_hieu_luc: Optional[str] = Field(None, description="Ngày hết hiệu lực")
    nguon_thu_thap: Optional[str] = Field(None, description="Nguồn thu thập")
    ngay_dang_cong_bao: Optional[str] = Field(None, description="Ngày đăng công báo")
    nganh: Optional[str] = Field(None, description="Ngành")
    linh_vuc: Optional[str] = Field(None, description="Lĩnh vực")
    chuc_danh: Optional[str] = Field(None, description="Chức danh người ký")
    nguoi_ky: Optional[str] = Field(None, description="Người ký")
    pham_vi: Optional[str] = Field(None, description="Phạm vi")
    thong_tin_ap_dung: Optional[str] = Field(None, description="Thông tin áp dụng")
    content_html: Optional[str] = Field(None, description="Nội dung HTML toàn văn")


class LawUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, description="Tiêu đề văn bản")
    so_ky_hieu: Optional[str] = Field(None, description="Số ký hiệu")
    ngay_ban_hanh: Optional[str] = Field(None, description="Ngày ban hành")
    loai_van_ban: Optional[str] = Field(None, description="Loại văn bản")
    co_quan_ban_hanh: Optional[str] = Field(None, description="Cơ quan ban hành")
    tinh_trang_hieu_luc: Optional[str] = Field(None, description="Tình trạng hiệu lực")
    ngay_co_hieu_luc: Optional[str] = Field(None, description="Ngày có hiệu lực")
    ngay_het_hieu_luc: Optional[str] = Field(None, description="Ngày hết hiệu lực")
    nguon_thu_thap: Optional[str] = Field(None, description="Nguồn thu thập")
    ngay_dang_cong_bao: Optional[str] = Field(None, description="Ngày đăng công báo")
    nganh: Optional[str] = Field(None, description="Ngành")
    linh_vuc: Optional[str] = Field(None, description="Lĩnh vực")
    chuc_danh: Optional[str] = Field(None, description="Chức danh người ký")
    nguoi_ky: Optional[str] = Field(None, description="Người ký")
    pham_vi: Optional[str] = Field(None, description="Phạm vi")
    thong_tin_ap_dung: Optional[str] = Field(None, description="Thông tin áp dụng")
    content_html: Optional[str] = Field(None, description="Nội dung HTML toàn văn")


# ╔══════════════════════════════════════════════════════════════╗
# ║                     ÁN LỆ (anle_documents)                 ║
# ╚══════════════════════════════════════════════════════════════╝

class AnleCreate(BaseModel):
    doc_name: str = Field(..., min_length=1, description="Mã văn bản (unique)")
    title: str = Field(..., min_length=1, description="Tiêu đề bản án")
    doc_code: Optional[str] = Field(None, description="Số hiệu")
    doc_type: Optional[str] = Field(None, description="Loại văn bản")
    case_type: Optional[str] = Field(None, description="Loại vụ án")
    doc_subtype: Optional[str] = Field(None, description="Phân loại phụ")
    year: Optional[int] = Field(None, description="Năm")
    issue_date: Optional[str] = Field(None, description="Ngày ban hành")
    issuing_authority: Optional[str] = Field(None, description="Cơ quan ban hành")
    court_level: Optional[str] = Field(None, description="Cấp tòa")
    jurisdiction: Optional[str] = Field(None, description="Thẩm quyền")
    subject: Optional[str] = Field(None, description="Chủ đề")
    markdown: Optional[str] = Field(None, description="Toàn văn markdown")
    precedent_number: Optional[str] = Field(None, description="Số Án Lệ (nếu có)")
    adopted_date: Optional[str] = Field(None, description="Ngày thông qua")
    applied_article_code: Optional[str] = Field(None, description="Mã điều luật áp dụng")
    principle_text: Optional[str] = Field(None, description="Nguyên tắc pháp lý")
    pdf_url: Optional[str] = Field(None, description="URL file PDF")


class AnleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, description="Tiêu đề bản án")
    doc_code: Optional[str] = Field(None, description="Số hiệu")
    doc_type: Optional[str] = Field(None, description="Loại văn bản")
    case_type: Optional[str] = Field(None, description="Loại vụ án")
    doc_subtype: Optional[str] = Field(None, description="Phân loại phụ")
    year: Optional[int] = Field(None, description="Năm")
    issue_date: Optional[str] = Field(None, description="Ngày ban hành")
    issuing_authority: Optional[str] = Field(None, description="Cơ quan ban hành")
    court_level: Optional[str] = Field(None, description="Cấp tòa")
    jurisdiction: Optional[str] = Field(None, description="Thẩm quyền")
    subject: Optional[str] = Field(None, description="Chủ đề")
    markdown: Optional[str] = Field(None, description="Toàn văn markdown")
    precedent_number: Optional[str] = Field(None, description="Số Án Lệ")
    adopted_date: Optional[str] = Field(None, description="Ngày thông qua")
    applied_article_code: Optional[str] = Field(None, description="Mã điều luật áp dụng")
    principle_text: Optional[str] = Field(None, description="Nguyên tắc pháp lý")
    pdf_url: Optional[str] = Field(None, description="URL file PDF")


# ╔══════════════════════════════════════════════════════════════╗
# ║                  PHÁP ĐIỂN (phapdien_articles)              ║
# ╚══════════════════════════════════════════════════════════════╝

class PhapdienCreate(BaseModel):
    article_anchor: str = Field(..., min_length=1, description="Mã định danh Điều khoản (unique)")
    article_title: str = Field(..., min_length=1, description="Tiêu đề Điều khoản")
    chapter_title: Optional[str] = Field(None, description="Tiêu đề Chương")
    subject_id: Optional[str] = Field(None, description="Mã Đề mục")
    subject_title: Optional[str] = Field(None, description="Tên Đề mục")
    topic_id: Optional[str] = Field(None, description="Mã Chủ đề")
    topic_number: Optional[int] = Field(None, description="Số thứ tự Chủ đề")
    topic_title: Optional[str] = Field(None, description="Tên Chủ đề")
    content_text: Optional[str] = Field(None, description="Nội dung văn bản")
    source_url: Optional[str] = Field(None, description="URL nguồn")
    source_note_text: Optional[str] = Field(None, description="Ghi chú nguồn")
    related_note_text: Optional[str] = Field(None, description="Ghi chú liên quan")


class PhapdienUpdate(BaseModel):
    article_title: Optional[str] = Field(None, min_length=1, description="Tiêu đề Điều khoản")
    chapter_title: Optional[str] = Field(None, description="Tiêu đề Chương")
    subject_id: Optional[str] = Field(None, description="Mã Đề mục")
    subject_title: Optional[str] = Field(None, description="Tên Đề mục")
    topic_id: Optional[str] = Field(None, description="Mã Chủ đề")
    topic_number: Optional[int] = Field(None, description="Số thứ tự Chủ đề")
    topic_title: Optional[str] = Field(None, description="Tên Chủ đề")
    content_text: Optional[str] = Field(None, description="Nội dung văn bản")
    source_url: Optional[str] = Field(None, description="URL nguồn")
    source_note_text: Optional[str] = Field(None, description="Ghi chú nguồn")
    related_note_text: Optional[str] = Field(None, description="Ghi chú liên quan")


# ╔══════════════════════════════════════════════════════════════╗
# ║                     COMMON RESPONSE                         ║
# ╚══════════════════════════════════════════════════════════════╝

class CrudResponse(BaseModel):
    ok: bool
    message: str
    id: Optional[str] = None
