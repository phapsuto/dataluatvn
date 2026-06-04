from typing import Optional, List
from pydantic import BaseModel


class AnleBrief(BaseModel):
    doc_name: str
    title: str
    doc_code: Optional[str] = None
    doc_type: Optional[str] = None
    case_type: Optional[str] = None
    year: Optional[int] = None
    court_level: Optional[str] = None
    precedent_number: Optional[str] = None


class AnleDetail(AnleBrief):
    doc_subtype: Optional[str] = None
    issue_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    jurisdiction: Optional[str] = None
    subject: Optional[str] = None
    markdown: Optional[str] = None
    num_pages: Optional[int] = None
    text_hash: Optional[str] = None
    adopted_date: Optional[str] = None
    applied_article_code: Optional[str] = None
    principle_text: Optional[str] = None
    pdf_url: Optional[str] = None


class PaginatedAnleResponse(BaseModel):
    total: int
    limit: int
    offset: int
    total_pages: int
    current_page: int
    has_next: bool
    has_previous: bool
    results: List[AnleBrief]
