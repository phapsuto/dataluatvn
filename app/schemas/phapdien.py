from typing import Optional, List
from pydantic import BaseModel


class PhapdienArticleBrief(BaseModel):
    article_anchor: str
    article_title: str
    subject_title: Optional[str] = None
    topic_title: Optional[str] = None


class PhapdienArticleDetail(PhapdienArticleBrief):
    chapter_title: Optional[str] = None
    subject_id: Optional[str] = None
    topic_id: Optional[str] = None
    topic_number: Optional[int] = None
    content_text: Optional[str] = None
    content_word_count: Optional[int] = None
    source_url: Optional[str] = None
    source_note_text: Optional[str] = None
    related_note_text: Optional[str] = None


class PaginatedPhapdienResponse(BaseModel):
    total: int
    limit: int
    offset: int
    total_pages: int
    current_page: int
    has_next: bool
    has_previous: bool
    results: List[PhapdienArticleBrief]


class GlossaryItem(BaseModel):
    id: int
    category: Optional[str] = None
    vi: str
    en: str
    note: Optional[str] = None
