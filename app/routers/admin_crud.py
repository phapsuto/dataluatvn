"""
Admin CRUD Router — API endpoints cho admin chỉnh sửa dữ liệu.
Tất cả endpoints yêu cầu JWT (admin đăng nhập).

Bao gồm:
  - /admin/laws/*           → CRUD cho văn bản pháp luật (documents)
  - /admin/anle/*           → CRUD cho Án Lệ (anle_documents)
  - /admin/phapdien/*       → CRUD cho Pháp Điển (phapdien_articles)
"""

import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, HTTPException, Body

from app.dependencies import require_jwt
from app.database import get_db_connection, get_content_connection
from app.config import DB_NAME, CONTENT_DB
from app.schemas.admin_crud import (
    LawCreate, LawUpdate,
    AnleCreate, AnleUpdate,
    PhapdienCreate, PhapdienUpdate,
    CrudResponse,
)

router = APIRouter(prefix="/admin", tags=["🛠️ Admin CRUD"])


# ╔══════════════════════════════════════════════════════════════╗
# ║                     LAWS CRUD                               ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/laws", response_model=CrudResponse, summary="Tạo văn bản mới")
def create_law(data: LawCreate, _user=Depends(require_jwt)):
    """Tạo một văn bản pháp luật mới. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Lấy next ID
    cursor.execute("SELECT MAX(id) FROM documents")
    max_id = cursor.fetchone()[0] or 0
    new_id = max_id + 1

    has_content = 1 if data.content_html else 0

    cursor.execute("""
        INSERT INTO documents (
            id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban,
            co_quan_ban_hanh, tinh_trang_hieu_luc, ngay_co_hieu_luc,
            ngay_het_hieu_luc, nguon_thu_thap, ngay_dang_cong_bao,
            nganh, linh_vuc, chuc_danh, nguoi_ky, pham_vi,
            thong_tin_ap_dung, has_content
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_id, data.title, data.so_ky_hieu, data.ngay_ban_hanh,
        data.loai_van_ban, data.co_quan_ban_hanh, data.tinh_trang_hieu_luc,
        data.ngay_co_hieu_luc, data.ngay_het_hieu_luc, data.nguon_thu_thap,
        data.ngay_dang_cong_bao, data.nganh, data.linh_vuc,
        data.chuc_danh, data.nguoi_ky, data.pham_vi,
        data.thong_tin_ap_dung, has_content,
    ))

    # Update FTS index
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
            (new_id, data.title, data.so_ky_hieu),
        )
    except sqlite3.OperationalError:
        pass  # FTS table might not exist

    conn.commit()
    conn.close()

    # Lưu content_html vào content_store.db
    if data.content_html:
        content_conn = get_content_connection()
        if content_conn:
            content_conn.execute(
                "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
                (new_id, data.content_html),
            )
            content_conn.commit()
            content_conn.close()

    return CrudResponse(ok=True, message=f"Đã tạo văn bản ID {new_id}", id=str(new_id))


@router.put("/laws/{law_id}", response_model=CrudResponse, summary="Cập nhật văn bản")
def update_law(
    law_id: int = Path(..., description="ID văn bản cần sửa"),
    data: LawUpdate = Body(...),
    _user=Depends(require_jwt),
):
    """Cập nhật thông tin văn bản pháp luật. Chỉ cập nhật các trường được gửi lên. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check exists
    cursor.execute("SELECT id FROM documents WHERE id = ?", (law_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản ID {law_id}")

    # Build dynamic UPDATE
    update_fields = []
    params = []
    update_data = data.model_dump(exclude_unset=True)

    # Tách content_html ra xử lý riêng
    content_html = update_data.pop("content_html", None)

    for field, value in update_data.items():
        update_fields.append(f"{field} = ?")
        params.append(value)

    if content_html is not None:
        update_fields.append("has_content = ?")
        params.append(1 if content_html else 0)

    if update_fields:
        params.append(law_id)
        cursor.execute(
            f"UPDATE documents SET {', '.join(update_fields)} WHERE id = ?",
            params,
        )

        # Update FTS
        if "title" in update_data or "so_ky_hieu" in update_data:
            cursor.execute("SELECT title, so_ky_hieu FROM documents WHERE id = ?", (law_id,))
            row = cursor.fetchone()
            if row:
                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
                        (law_id, row["title"], row["so_ky_hieu"]),
                    )
                except sqlite3.OperationalError:
                    pass

        conn.commit()

    conn.close()

    # Update content_html
    if content_html is not None:
        content_conn = get_content_connection()
        if content_conn:
            content_conn.execute(
                "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
                (law_id, content_html),
            )
            content_conn.commit()
            content_conn.close()

    return CrudResponse(ok=True, message=f"Đã cập nhật văn bản ID {law_id}", id=str(law_id))


@router.delete("/laws/{law_id}", response_model=CrudResponse, summary="Xóa văn bản")
def delete_law(
    law_id: int = Path(..., description="ID văn bản cần xóa"),
    _user=Depends(require_jwt),
):
    """Xóa vĩnh viễn một văn bản và các dữ liệu liên quan. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title FROM documents WHERE id = ?", (law_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản ID {law_id}")

    title = row["title"]

    # Delete from FTS
    try:
        cursor.execute("DELETE FROM documents_fts WHERE rowid = ?", (law_id,))
    except sqlite3.OperationalError:
        pass

    # Delete relationships
    cursor.execute("DELETE FROM relationships WHERE doc_id = ? OR other_doc_id = ?", (law_id, law_id))

    # Delete article_modifications
    try:
        cursor.execute("DELETE FROM article_modifications WHERE doc_id = ? OR modified_by_doc_id = ?", (law_id, law_id))
    except sqlite3.OperationalError:
        pass

    # Delete document
    cursor.execute("DELETE FROM documents WHERE id = ?", (law_id,))
    conn.commit()
    conn.close()

    # Delete content
    content_conn = get_content_connection()
    if content_conn:
        content_conn.execute("DELETE FROM document_content WHERE doc_id = ?", (law_id,))
        content_conn.commit()
        content_conn.close()

    return CrudResponse(ok=True, message=f"Đã xóa văn bản: {title[:60]}", id=str(law_id))


# ╔══════════════════════════════════════════════════════════════╗
# ║                     ÁN LỆ CRUD                             ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/anle", response_model=CrudResponse, summary="Tạo Án Lệ mới")
def create_anle(data: AnleCreate, _user=Depends(require_jwt)):
    """Tạo một bản án / án lệ mới. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check duplicate
    cursor.execute("SELECT doc_name FROM anle_documents WHERE doc_name = ?", (data.doc_name,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail=f"Án Lệ với doc_name '{data.doc_name}' đã tồn tại")

    # Tính toán thêm fields
    char_len = len(data.markdown) if data.markdown else 0

    cursor.execute("""
        INSERT INTO anle_documents (
            doc_name, title, doc_code, doc_type, case_type, doc_subtype,
            year, issue_date, issuing_authority, court_level, jurisdiction,
            subject, markdown, char_len, precedent_number, adopted_date,
            applied_article_code, principle_text, pdf_url,
            source, parsed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'admin', ?)
    """, (
        data.doc_name, data.title, data.doc_code, data.doc_type,
        data.case_type, data.doc_subtype, data.year, data.issue_date,
        data.issuing_authority, data.court_level, data.jurisdiction,
        data.subject, data.markdown, char_len, data.precedent_number,
        data.adopted_date, data.applied_article_code, data.principle_text,
        data.pdf_url, datetime.now(timezone.utc).isoformat(),
    ))

    # Update FTS
    try:
        rowid = cursor.lastrowid
        cursor.execute(
            "INSERT OR REPLACE INTO anle_fts (rowid, title, subject, principle_text) VALUES (?, ?, ?, ?)",
            (rowid, data.title, data.subject, data.principle_text),
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã tạo Án Lệ: {data.doc_name}", id=data.doc_name)


@router.put("/anle/{doc_name}", response_model=CrudResponse, summary="Cập nhật Án Lệ")
def update_anle(
    doc_name: str = Path(..., description="Mã doc_name cần sửa"),
    data: AnleUpdate = Body(...),
    _user=Depends(require_jwt),
):
    """Cập nhật thông tin Án Lệ. Chỉ cập nhật các trường được gửi lên. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT rowid, doc_name FROM anle_documents WHERE doc_name = ?", (doc_name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Án Lệ: {doc_name}")

    rowid = row["rowid"]
    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        conn.close()
        return CrudResponse(ok=True, message="Không có trường nào cần cập nhật", id=doc_name)

    # Recalculate char_len if markdown changed
    if "markdown" in update_data:
        update_data["char_len"] = len(update_data["markdown"]) if update_data["markdown"] else 0

    update_fields = [f"{k} = ?" for k in update_data.keys()]
    params = list(update_data.values()) + [doc_name]

    cursor.execute(
        f"UPDATE anle_documents SET {', '.join(update_fields)} WHERE doc_name = ?",
        params,
    )

    # Update FTS
    if any(k in update_data for k in ("title", "subject", "principle_text")):
        cursor.execute(
            "SELECT title, subject, principle_text FROM anle_documents WHERE doc_name = ?",
            (doc_name,),
        )
        updated = cursor.fetchone()
        if updated:
            try:
                cursor.execute(
                    "INSERT OR REPLACE INTO anle_fts (rowid, title, subject, principle_text) VALUES (?, ?, ?, ?)",
                    (rowid, updated["title"], updated["subject"], updated["principle_text"]),
                )
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã cập nhật Án Lệ: {doc_name}", id=doc_name)


@router.delete("/anle/{doc_name}", response_model=CrudResponse, summary="Xóa Án Lệ")
def delete_anle(
    doc_name: str = Path(..., description="Mã doc_name cần xóa"),
    _user=Depends(require_jwt),
):
    """Xóa vĩnh viễn một bản án / án lệ. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT rowid, doc_name, title FROM anle_documents WHERE doc_name = ?", (doc_name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Án Lệ: {doc_name}")

    title = row["title"]
    rowid = row["rowid"]

    # Delete FTS
    try:
        cursor.execute("DELETE FROM anle_fts WHERE rowid = ?", (rowid,))
    except sqlite3.OperationalError:
        pass

    # Delete crosslinks
    try:
        cursor.execute("DELETE FROM crosslinks WHERE anle_doc_name = ?", (doc_name,))
    except sqlite3.OperationalError:
        pass

    cursor.execute("DELETE FROM anle_documents WHERE doc_name = ?", (doc_name,))
    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã xóa Án Lệ: {title[:60]}", id=doc_name)


# ╔══════════════════════════════════════════════════════════════╗
# ║                    PHÁP ĐIỂN CRUD                           ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/phapdien", response_model=CrudResponse, summary="Tạo Điều khoản Pháp Điển mới")
def create_phapdien(data: PhapdienCreate, _user=Depends(require_jwt)):
    """Tạo một Điều khoản Pháp Điển mới. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check duplicate
    cursor.execute("SELECT article_anchor FROM phapdien_articles WHERE article_anchor = ?", (data.article_anchor,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail=f"Điều khoản '{data.article_anchor}' đã tồn tại")

    # Tính toán thêm
    content_char_len = len(data.content_text) if data.content_text else 0
    content_word_count = len(data.content_text.split()) if data.content_text else 0

    cursor.execute("""
        INSERT INTO phapdien_articles (
            article_anchor, article_title, chapter_title,
            subject_id, subject_title, topic_id, topic_number, topic_title,
            content_text, content_char_len, content_word_count,
            source_url, source_note_text, related_note_text,
            scraped_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'admin')
    """, (
        data.article_anchor, data.article_title, data.chapter_title,
        data.subject_id, data.subject_title, data.topic_id,
        data.topic_number, data.topic_title, data.content_text,
        content_char_len, content_word_count,
        data.source_url, data.source_note_text, data.related_note_text,
        datetime.now(timezone.utc).isoformat(),
    ))

    # Update FTS
    try:
        rowid = cursor.lastrowid
        cursor.execute(
            "INSERT OR REPLACE INTO phapdien_fts (rowid, article_title, content_text) VALUES (?, ?, ?)",
            (rowid, data.article_title, data.content_text),
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã tạo Điều khoản: {data.article_anchor}", id=data.article_anchor)


@router.put("/phapdien/{article_anchor:path}", response_model=CrudResponse, summary="Cập nhật Điều khoản")
def update_phapdien(
    article_anchor: str = Path(..., description="Mã định danh Điều khoản"),
    data: PhapdienUpdate = Body(...),
    _user=Depends(require_jwt),
):
    """Cập nhật thông tin Điều khoản Pháp Điển. Chỉ cập nhật các trường được gửi lên. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT rowid, article_anchor FROM phapdien_articles WHERE article_anchor = ?", (article_anchor,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Điều khoản: {article_anchor}")

    rowid = row["rowid"]
    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        conn.close()
        return CrudResponse(ok=True, message="Không có trường nào cần cập nhật", id=article_anchor)

    # Recalculate lengths if content changed
    if "content_text" in update_data:
        ct = update_data["content_text"] or ""
        update_data["content_char_len"] = len(ct)
        update_data["content_word_count"] = len(ct.split())

    update_fields = [f"{k} = ?" for k in update_data.keys()]
    params = list(update_data.values()) + [article_anchor]

    cursor.execute(
        f"UPDATE phapdien_articles SET {', '.join(update_fields)} WHERE article_anchor = ?",
        params,
    )

    # Update FTS
    if any(k in update_data for k in ("article_title", "content_text")):
        cursor.execute(
            "SELECT article_title, content_text FROM phapdien_articles WHERE article_anchor = ?",
            (article_anchor,),
        )
        updated = cursor.fetchone()
        if updated:
            try:
                cursor.execute(
                    "INSERT OR REPLACE INTO phapdien_fts (rowid, article_title, content_text) VALUES (?, ?, ?)",
                    (rowid, updated["article_title"], updated["content_text"]),
                )
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã cập nhật Điều khoản: {article_anchor}", id=article_anchor)


@router.delete("/phapdien/{article_anchor:path}", response_model=CrudResponse, summary="Xóa Điều khoản")
def delete_phapdien(
    article_anchor: str = Path(..., description="Mã định danh Điều khoản"),
    _user=Depends(require_jwt),
):
    """Xóa vĩnh viễn một Điều khoản Pháp Điển. **Yêu cầu đăng nhập admin.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT rowid, article_anchor, article_title FROM phapdien_articles WHERE article_anchor = ?", (article_anchor,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Điều khoản: {article_anchor}")

    title = row["article_title"]
    rowid = row["rowid"]

    # Delete FTS
    try:
        cursor.execute("DELETE FROM phapdien_fts WHERE rowid = ?", (rowid,))
    except sqlite3.OperationalError:
        pass

    # Delete crosslinks
    try:
        cursor.execute("DELETE FROM crosslinks WHERE phapdien_anchor = ?", (article_anchor,))
    except sqlite3.OperationalError:
        pass

    cursor.execute("DELETE FROM phapdien_articles WHERE article_anchor = ?", (article_anchor,))
    conn.commit()
    conn.close()

    return CrudResponse(ok=True, message=f"Đã xóa Điều khoản: {title[:60]}", id=article_anchor)
