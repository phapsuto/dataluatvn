from typing import Optional, List, Dict
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    message: str
    total_documents_loaded: int
    docs_url: str
    redoc_url: str
    admin_url: str


class LawBrief(BaseModel):
    id: int
    title: str
    so_ky_hieu: Optional[str] = None
    ngay_ban_hanh: Optional[str] = None
    loai_van_ban: Optional[str] = None
    co_quan_ban_hanh: Optional[str] = None
    tinh_trang_hieu_luc: Optional[str] = None


class LawDetail(LawBrief):
    ngay_co_hieu_luc: Optional[str] = None
    ngay_het_hieu_luc: Optional[str] = None
    nguon_thu_thap: Optional[str] = None
    ngay_dang_cong_bao: Optional[str] = None
    nganh: Optional[str] = None
    linh_vuc: Optional[str] = None
    chuc_danh: Optional[str] = None
    nguoi_ky: Optional[str] = None
    pham_vi: Optional[str] = None
    thong_tin_ap_dung: Optional[str] = None
    content_html: Optional[str] = None


class RelationshipInfo(BaseModel):
    doc_id: int
    other_doc_id: int
    relationship: str
    other_doc_title: str
    other_doc_so_ky_hieu: Optional[str] = None


class ArticleModification(BaseModel):
    article_name: str
    modified_text: str
    modified_by_doc_id: int


class StatsResponse(BaseModel):
    total_documents: int
    total_relationships: int
    by_document_type: Dict[str, int]
    by_effectiveness_status: Dict[str, int]


class PaginatedSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    total_pages: int
    current_page: int
    has_next: bool
    has_previous: bool
    results: List[LawBrief]


class CategoryItem(BaseModel):
    name: str
    count: int


class ErrorResponse(BaseModel):
    detail: str


class ProvinceItem(BaseModel):
    code: str
    name: str
    full_name: str
    code_name: Optional[str] = None
    administrative_unit_id: Optional[int] = None


class WardItem(BaseModel):
    code: str
    name: str
    full_name: str
    code_name: Optional[str] = None
    province_code: str
    administrative_unit_id: Optional[int] = None


class ChunkBrief(BaseModel):
    id: int
    doc_id: int
    chunk_index: int
    chunk_type: str
    chunk_header: Optional[str] = None
    chunk_text: str
    token_estimate: Optional[int] = None
    document_title: Optional[str] = None
    document_so_ky_hieu: Optional[str] = None
    document_loai_van_ban: Optional[str] = None
    document_co_quan_ban_hanh: Optional[str] = None
    document_tinh_trang_hieu_luc: Optional[str] = None
    document_ngay_ban_hanh: Optional[str] = None
    score: Optional[float] = None


class PaginatedChunkSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    total_pages: int
    current_page: int
    has_next: bool
    has_previous: bool
    results: List[ChunkBrief]


