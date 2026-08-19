#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GÁN LẠI NHÃN: QUYẾT ĐỊNH đang bị xếp nhầm thành BẢN ÁN.

VÌ SAO CẦN (phát hiện 19/8/2026):
Mục "Thực hành nghiên cứu hồ sơ" của app Trợ lý VKS xin kho một BẢN ÁN để học viên nghiên
cứu, nhưng phần lớn lượt xin đều nhận về thứ không dùng được, phải bấm lấy lại nhiều lần.

Truy ra: trong kho, gần một nửa tài liệu gắn nhãn `loai_tai_lieu='BAN_AN'` thật ra là
QUYẾT ĐỊNH tố tụng — đọc số hiệu là thấy: "1797/2025/QĐST-DS", "01/2025/QĐ-PT",
"138/2025/QĐST-HNGĐ". Đó là quyết định đình chỉ, công nhận sự thoả thuận, áp dụng biện
pháp khẩn cấp tạm thời… — văn bản 1.300–2.800 ký tự, KHÔNG có phần "NHẬN ĐỊNH CỦA TÒA ÁN",
nên không thể dùng làm bài nghiên cứu hồ sơ (không có gì để đối chiếu lập luận).

Đo trên kho: 300 bản án dân sự thì chỉ 53 bản (17%) có mục nhận định — số còn lại chính là
quyết định bị xếp nhầm.

CÁCH NHẬN BIẾT: mã trong số hiệu. Bản án thật mang mã lĩnh vực + cấp xét xử ("DS-ST",
"HS-ST", "KDTM-PT", "HNGĐ-ST"); quyết định mang mã bắt đầu bằng "QĐ" ("QĐST-DS", "QĐ-PT").

Chạy thử trước rồi mới chạy thật:
    python3 gan_lai_nhan_quyet_dinh.py --db <đường dẫn> --thu
    python3 gan_lai_nhan_quyet_dinh.py --db <đường dẫn>
"""
import os
import re
import sqlite3
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else os.path.join(BASE, "chebien", "nghiep_vu_corpus.db")
CHI_THU = "--thu" in sys.argv

# Mã trong số hiệu: "1797/2025/QĐST-DS" → nhóm bắt được là "QĐST-DS".
# Cho phép khoảng trắng rải rác vì chữ bóc từ PDF hay vỡ ("Số: 01/2025 /QĐ - PT").
MA_SO_HIEU = re.compile(r"\d{1,4}\s*/\s*20\d{2}\s*/\s*([A-ZĐ][A-ZĐ\s–-]{1,12})")


def la_quyet_dinh(van_dau: str) -> bool:
    m = MA_SO_HIEU.search(re.sub(r"\s+", " ", van_dau or ""))
    if not m:
        return False
    ma = re.sub(r"\s+", "", m.group(1))
    return ma.startswith("QĐ")


def _run():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=15000")
    cur = con.cursor()

    rows = cur.execute(
        """SELECT d.id, substr(group_concat(c.noi_dung, ' '), 1, 700)
           FROM docs d JOIN chunks c ON c.doc_id = d.id
           WHERE d.loai_tai_lieu = 'BAN_AN'
           GROUP BY d.id"""
    ).fetchall()

    doi = [doc_id for doc_id, dau in rows if la_quyet_dinh(dau)]
    print(f"tài liệu đang gắn nhãn BAN_AN: {len(rows)}")
    print(f"{'[CHỈ THỬ] ' if CHI_THU else ''}thực ra là QUYẾT ĐỊNH: {len(doi)}"
          f" ({len(doi) * 100 // max(1, len(rows))}%)", flush=True)

    if not CHI_THU and doi:
        for i in range(0, len(doi), 400):
            phan = doi[i:i + 400]
            qm = ",".join("?" * len(phan))
            cur.execute(f"UPDATE docs SET loai_tai_lieu='QUYET_DINH' WHERE id IN ({qm})", phan)
            cur.execute(f"UPDATE chunks SET loai_tai_lieu='QUYET_DINH' WHERE doc_id IN ({qm})", phan)
        con.commit()
        con_lai = cur.execute("SELECT COUNT(*) FROM docs WHERE loai_tai_lieu='BAN_AN'").fetchone()[0]
        print(f"đã gán lại nhãn. Còn {con_lai} BẢN ÁN thật.", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    _run()
