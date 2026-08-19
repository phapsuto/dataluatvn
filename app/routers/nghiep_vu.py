"""KHO HỌC LIỆU NGHIỆP VỤ KIỂM SÁT — tra cứu corpus nghiệp vụ (nghiep_vu_corpus.db).

VÌ SAO CÓ TỆP NÀY: dự án Kiểm sát (vks-app-document) có bốn tính năng gọi thẳng vào
`/nghiep-vu/search` và `/nghiep-vu/doc/{id}`:
    - Tra cứu học liệu          (/hoc-tap/tra-cuu)
    - Học đối thoại Socratic    (/api/hoc-tap/socratic)
    - Thực hành nghiên cứu hồ sơ + học liệu bù  (/api/luyen-an/*)
    - Trình đọc văn bản gốc     (/api/hoc-tap/van-ban)
Kho đã dựng xong (9.144 văn bản / 47.204 đoạn) nhưng CHƯA CÓ ĐƯỜNG HTTP nào phục vụ —
đo ngày 19/8/2026: cả bốn tính năng trả 502 vì API trả 404 cho mọi đường /nghiep-vu.

Tìm bằng FTS5 (BM25) của chính SQLite, KHÔNG cần model nhúng hay FAISS: kho có sẵn bảng
`chunks_fts` trên trường noi_dung_ctx. Nhờ vậy đường này chạy được ở máy chủ mà không
tốn thêm RAM cho model — đúng chỗ nghẽn của máy chủ dùng chung.
"""
import os
import re
import sqlite3
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import require_api_key

router = APIRouter(prefix="/nghiep-vu", tags=["📚 Học liệu nghiệp vụ Kiểm sát"])

# Đường dẫn khác nhau giữa máy lập trình (hoc_lieu/chebien/) và máy chủ (thư mục gốc dự
# án) — dò lần lượt thay vì bắt người triển khai nhớ đặt biến môi trường.
_UNG_VIEN = [
    os.environ.get("NGHIEP_VU_DB_PATH", ""),
    "nghiep_vu_corpus.db",
    os.path.join("hoc_lieu", "chebien", "nghiep_vu_corpus.db"),
]


def _duong_db() -> str:
    for p in _UNG_VIEN:
        if p and os.path.exists(p):
            return p
    raise HTTPException(503, "Kho học liệu nghiệp vụ chưa được nạp trên máy chủ này")


def _ket_noi() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{_duong_db()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _cau_fts(q: str) -> str:
    """Đổi câu hỏi người dùng thành truy vấn FTS5 an toàn.

    Người dùng gõ tự nhiên ("khởi tố bị can khi nào?"), mà FTS5 coi ", ? - * : ( )" là
    toán tử — để nguyên là câu truy vấn hỏng và API trả 500. Bọc từng từ trong ngoặc kép
    rồi nối bằng OR: giữ được mọi dấu tiếng Việt, không từ nào thành toán tử.
    """
    tu = [t for t in re.split(r"[^0-9A-Za-zÀ-ỹ]+", q) if len(t) > 1]
    if not tu:
        raise HTTPException(400, "Từ khoá tra cứu quá ngắn")
    return " OR ".join(f'"{t}"' for t in tu[:24])


@router.get("/search", summary="Tra cứu học liệu nghiệp vụ (BM25)")
def tra_cuu(
    q: str = Query(..., min_length=2, max_length=300, description="Từ khoá tra cứu"),
    loai: Optional[str] = Query(None, description="Lọc theo loại tài liệu, ví dụ BAN_AN"),
    mon: Optional[str] = Query(None, pattern=r"^M\d{2}$", description="Lọc theo môn M01..M13"),
    linh_vuc: Optional[str] = Query(
        None, pattern=r"^[a-z_]{2,20}$",
        description="Lọc theo lĩnh vực bản án: hinh_su, dan_su, hngd, kdtm, hanh_chinh, lao_dong",
    ),
    limit: int = Query(15, ge=1, le=50),
    per_doc: int = Query(0, ge=0, le=10, description="Tối đa bao nhiêu đoạn cho MỖI văn bản (0 = không giới hạn)"),
    _key=Depends(require_api_key),
) -> Dict[str, Any]:
    """Tìm đoạn học liệu khớp từ khoá. **Yêu cầu API Key.**"""
    con = _ket_noi()
    try:
        dieu_kien, tham_so = ["chunks_fts MATCH ?"], [_cau_fts(q)]
        if loai:
            dieu_kien.append("c.loai_tai_lieu = ?")
            tham_so.append(loai)
        if mon:
            dieu_kien.append("c.mon = ?")
            tham_so.append(mon)
        if linh_vuc:
            # Lĩnh vực nằm trong docs.ghi_chu dạng "linh_vuc=dan_su;..." — cả 439 bản án
            # đều có (đã đếm). Không lọc ở đây thì bên gọi phải tải về rồi tự loại, và
            # phần lớn ứng viên rơi sai lĩnh vực: đo thật ở Thực hành nghiên cứu hồ sơ,
            # chỉ 2/18 lượt lấy được ca, 16 lượt còn lại báo "chưa có bản án đọc được".
            dieu_kien.append("(d.ghi_chu = ? OR d.ghi_chu LIKE ?)")
            tham_so += [f"linh_vuc={linh_vuc}", f"linh_vuc={linh_vuc};%"]

        # Lấy dư khi có per_doc: lọc bớt theo văn bản diễn ra sau khi xếp hạng, không lấy
        # dư thì "mỗi văn bản 1 đoạn" cắt còn vài kết quả.
        so_lay = limit * 8 if per_doc else limit
        sql = f"""
            SELECT c.id, c.doc_id, c.chunk_type, c.header, c.noi_dung, c.mon,
                   c.loai_tai_lieu, d.ten, d.so_hieu, d.nguon, d.ngay,
                   d.authority_level, d.effective_status, d.source_url,
                   bm25(chunks_fts) AS diem
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN docs   d ON d.id = c.doc_id
            WHERE {' AND '.join(dieu_kien)}
            ORDER BY diem
            LIMIT ?
        """
        hang = con.execute(sql, (*tham_so, so_lay)).fetchall()

        ket_qua, dem = [], {}
        for r in hang:
            if per_doc:
                n = dem.get(r["doc_id"], 0)
                if n >= per_doc:
                    continue
                dem[r["doc_id"]] = n + 1
            ket_qua.append({
                "chunk_id": r["id"],
                "doc_id": r["doc_id"],
                "chunk_type": r["chunk_type"],
                "header": r["header"] or "",
                "noi_dung": r["noi_dung"] or "",
                "mon": r["mon"],
                "loai_tai_lieu": r["loai_tai_lieu"],
                # bm25() của SQLite càng ÂM càng khớp — đảo dấu để bên gọi đọc theo lối
                # quen thuộc "điểm cao là khớp hơn".
                "diem": round(-float(r["diem"]), 4),
                "tai_lieu": {
                    "id": r["doc_id"],
                    "ten": r["ten"] or "",
                    "so_hieu": r["so_hieu"] or "",
                    "nguon": r["nguon"] or "",
                    "ngay": r["ngay"] or "",
                    "authority_level": r["authority_level"],
                    "effective_status": r["effective_status"],
                    "source_url": r["source_url"],
                },
            })
            if len(ket_qua) >= limit:
                break
        return {"total": len(ket_qua), "results": ket_qua}
    finally:
        con.close()


@router.get("/doc/{doc_id}", summary="Đọc toàn văn một văn bản học liệu")
def doc_toan_van(
    doc_id: int = Path(..., ge=1),
    _key=Depends(require_api_key),
) -> Dict[str, Any]:
    """Trả về siêu dữ liệu và TOÀN BỘ đoạn của văn bản, theo đúng thứ tự. **Yêu cầu API Key.**"""
    con = _ket_noi()
    try:
        d = con.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
        if d is None:
            raise HTTPException(404, "Không có văn bản này trong kho học liệu")
        chunks = con.execute(
            "SELECT id, chunk_type, header, noi_dung, mon, loai_tai_lieu FROM chunks WHERE doc_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()
        return {
            "doc": {
                "id": d["id"], "ten": d["ten"] or "", "so_hieu": d["so_hieu"] or "",
                "ngay": d["ngay"] or "", "nguon": d["nguon"] or "",
                "loai_tai_lieu": d["loai_tai_lieu"], "mon": d["mon"],
                "ghi_chu": d["ghi_chu"] or "",
                "authority_level": d["authority_level"],
                "effective_status": d["effective_status"],
                "source_url": d["source_url"],
            },
            "chunks": [dict(c) for c in chunks],
        }
    finally:
        con.close()


@router.get("/stats", summary="Thống kê kho học liệu nghiệp vụ")
def thong_ke(_key=Depends(require_api_key)) -> Dict[str, Any]:
    """Đếm nhanh kho — dùng để kiểm tra kho đã nạp đúng sau mỗi đợt dọn. **Yêu cầu API Key.**"""
    con = _ket_noi()
    try:
        return {
            "so_van_ban": con.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
            "so_doan": con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "theo_loai": {r[0] or "?": r[1] for r in con.execute(
                "SELECT loai_tai_lieu, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")},
            "theo_mon": {r[0] or "?": r[1] for r in con.execute(
                "SELECT mon, COUNT(*) FROM docs GROUP BY 1 ORDER BY 1")},
        }
    finally:
        con.close()
