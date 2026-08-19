#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CẮT PHẦN ĐẦU TRANG WEB DÍNH VÀO BẢN ÁN.

VÌ SAO CẦN (phát hiện 19/8/2026):
Mỗi bản án crawl về từ trang nguồn đều mang theo NGUYÊN GIAO DIỆN TRANG: form tìm kiếm
nâng cao và THANH BÊN MỤC LỤC BỘ LUẬT dài 623 dòng ("137.Tội công nhiên chiếm đoạt tài
sản (Bộ luật hình sự năm 1999)"). Đo trên kho: cả 1.024 bản án đều dính, không sót bản nào.

Hậu quả thấy được ở app Trợ lý VKS, mục "Thực hành nghiên cứu hồ sơ": học viên chọn lĩnh
vực DÂN SỰ nhưng nhận được một danh sách tội danh HÌNH SỰ, trong đó dẫn cả Bộ luật hình sự
năm 1999 ĐÃ HẾT HIỆU LỰC — vì đoạn cắt đề bài rơi trúng thanh bên đó.

CÁCH LÀM: lọc theo dòng không ăn (thanh bên bị gộp nhiều mục trên một dòng, chữ lại vỡ khi
bóc từ PDF). Nên dùng cấu trúc thay vì mẫu chữ: với một BẢN ÁN, mọi thứ nằm TRƯỚC mốc mở
đầu nghi thức đều là giao diện trang, cắt sạch.
Mốc mở đầu tìm trên BẢN NÉN (bỏ hết khoảng trắng) vì chữ bóc từ PDF hay vỡ ("Độc lậ p").

Chạy thử trước rồi mới chạy thật:
    python3 cat_dau_trang_ban_an.py --db <đường dẫn> --thu     # chỉ đếm, không sửa
    python3 cat_dau_trang_ban_an.py --db <đường dẫn>           # sửa thật
"""
import os
import re
import sqlite3
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else os.path.join(BASE, "chebien", "nghiep_vu_corpus.db")
CHI_THU = "--thu" in sys.argv

# Mốc mở đầu một bản án, theo thứ tự ưu tiên. Dò trên bản nén nên không có khoảng trắng.
MOC_MO_DAU = re.compile(
    r"CỘNGHÒAXÃHỘICHỦNGHĨAVIỆTNAM|NHÂNDANHNƯỚC|TÒAÁNNHÂNDÂN|TOÀÁNNHÂNDÂN|Bảnánsố|BẢNÁNSỐ"
)


def cat_dau(van: str):
    """Trả về (phần bản án, số ký tự đã cắt). Không thấy mốc thì trả nguyên văn."""
    nen_chars, vi_tri = [], []
    for i, ch in enumerate(van):
        if not ch.isspace():
            nen_chars.append(ch)
            vi_tri.append(i)
    nen = "".join(nen_chars)
    m = MOC_MO_DAU.search(nen)
    if not m:
        return van, 0
    dau = vi_tri[m.start()]
    return van[dau:], dau


def _run():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=15000")
    cur = con.cursor()

    doc_ids = [r[0] for r in cur.execute("SELECT id FROM docs WHERE loai_tai_lieu='BAN_AN'")]
    print(f"{len(doc_ids)} bản án cần soi...", flush=True)

    so_doc_sua = 0
    so_chunk_xoa = 0
    so_chunk_sua = 0
    tong_cat = 0

    for doc_id in doc_ids:
        chunks = cur.execute(
            "SELECT id, noi_dung, noi_dung_ctx FROM chunks WHERE doc_id=? ORDER BY id", (doc_id,)
        ).fetchall()
        if not chunks:
            continue

        # Tìm chunk ĐẦU TIÊN chứa mốc mở đầu bản án.
        vi_tri_moc = None
        for idx, (_cid, nd, _ctx) in enumerate(chunks):
            _, cat = cat_dau(nd or "")
            nen = re.sub(r"\s+", "", nd or "")
            if MOC_MO_DAU.search(nen):
                vi_tri_moc = (idx, cat)
                break
        if vi_tri_moc is None or (vi_tri_moc[0] == 0 and vi_tri_moc[1] == 0):
            continue  # không thấy mốc, hoặc bản án đã sạch sẵn

        idx_moc, cat_trong_chunk = vi_tri_moc
        so_doc_sua += 1

        # Mọi chunk TRƯỚC chunk chứa mốc đều là giao diện trang → xoá.
        for cid, nd, _ctx in chunks[:idx_moc]:
            tong_cat += len(nd or "")
            so_chunk_xoa += 1
            if not CHI_THU:
                cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
                cur.execute("DELETE FROM chunks WHERE id=?", (cid,))

        # Chunk chứa mốc: cắt bỏ phần đứng trước mốc.
        if cat_trong_chunk > 0:
            cid, nd, ctx = chunks[idx_moc]
            moi = (nd or "")[cat_trong_chunk:]
            tong_cat += cat_trong_chunk
            so_chunk_sua += 1
            if not CHI_THU:
                header = (ctx or "").split("\n", 1)[0]
                ctx_moi = header + "\n" + moi if header.startswith("«") else moi
                cur.execute("UPDATE chunks SET noi_dung=?, noi_dung_ctx=? WHERE id=?", (moi, ctx_moi, cid))
                cur.execute("UPDATE chunks_fts SET noi_dung_ctx=? WHERE rowid=?", (ctx_moi, cid))

        if not CHI_THU and so_doc_sua % 100 == 0:
            con.commit()

    if not CHI_THU:
        con.commit()
    print(
        f"{'[CHỈ THỬ] ' if CHI_THU else ''}bản án phải cắt đầu: {so_doc_sua}"
        f" | chunk xoá: {so_chunk_xoa} | chunk cắt bớt: {so_chunk_sua}"
        f" | tổng ký tự rác cắt đi: {tong_cat:,}",
        flush=True,
    )
    print("DONE", flush=True)


if __name__ == "__main__":
    _run()
