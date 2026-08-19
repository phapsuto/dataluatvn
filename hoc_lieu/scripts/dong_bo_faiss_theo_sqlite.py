#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ĐỒNG BỘ CHỈ MỤC FAISS THEO SQLITE — bỏ vector trỏ vào chunk đã xoá.

VÌ SAO CẦN: các bước dọn kho (cat_dau_trang_ban_an.py, clean_corpus_junk.py chạy với
--no-faiss) xoá chunk trong SQLite nhưng KHÔNG đụng chỉ mục FAISS. Để lệch như vậy thì tìm
kiếm ngữ nghĩa vẫn trả về id của chunk không còn tồn tại — người dùng nhận kết quả rỗng
hoặc dịch vụ báo lỗi, mà nhìn vào chỉ mục thì thấy "vẫn đủ vector" nên rất khó lần ra.

Đo sau đợt dọn 19/8/2026: FAISS 84.771 vector / SQLite còn 47.204 chunk → 38.959 vector mồ
côi.

Script này KHÔNG tính lại vector (không cần model, chạy được trên máy chủ): nó dựng chỉ mục
mới từ chính các vector cũ, chỉ giữ lại những vector còn chunk tương ứng.

    python3 dong_bo_faiss_theo_sqlite.py --thu     # chỉ đếm
    python3 dong_bo_faiss_theo_sqlite.py           # dựng lại, có sao lưu .bak
"""
import os
import shutil
import sqlite3
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CHEBIEN = os.path.join(BASE, "chebien")
DB = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else os.path.join(CHEBIEN, "nghiep_vu_corpus.db")
IDX = sys.argv[sys.argv.index("--index") + 1] if "--index" in sys.argv else os.path.join(CHEBIEN, "nghiep_vu_faiss.index")
IDMAP = os.path.splitext(IDX)[0] + "_ids.npy"
if not os.path.exists(IDMAP):
    IDMAP = os.path.join(CHEBIEN, "nghiep_vu_faiss_ids.npy")
CHI_THU = "--thu" in sys.argv


def _run():
    import numpy as np
    import faiss

    con = sqlite3.connect(DB)
    con_chunk = set(r[0] for r in con.execute("SELECT id FROM chunks"))
    ids = np.load(IDMAP)
    giu = [i for i, cid in enumerate(ids) if int(cid) in con_chunk]

    print(f"FAISS: {len(ids)} vector | SQLite: {len(con_chunk)} chunk")
    print(f"{'[CHỈ THỬ] ' if CHI_THU else ''}vector mồ côi cần bỏ: {len(ids) - len(giu)}", flush=True)
    if CHI_THU or len(giu) == len(ids):
        print("DONE", flush=True)
        return

    index = faiss.read_index(IDX)
    moi = faiss.IndexFlatIP(index.d)
    LO = 20000
    for i in range(0, len(giu), LO):
        phan = giu[i:i + LO]
        moi.add(np.vstack([index.reconstruct(int(p)) for p in phan]).astype("float32"))
        print(f"   ...{min(i + LO, len(giu))}/{len(giu)}", flush=True)

    # Sao lưu trước khi ghi đè — chỉ mục dựng lại được nhưng mất thì tốn cả buổi nhúng lại.
    for f in (IDX, IDMAP):
        if os.path.exists(f) and not os.path.exists(f + ".bak"):
            shutil.copy2(f, f + ".bak")

    faiss.write_index(moi, IDX)
    np.save(IDMAP, ids[giu])
    print(f"chỉ mục mới: {moi.ntotal} vector (khớp đúng SQLite)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    _run()
