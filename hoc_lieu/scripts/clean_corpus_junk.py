#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DỌN RÁC GIAO DIỆN WEB trong chunks của nghiep_vu_corpus:
hộp metadata ("Tình trạng hiệu lực / Ngôn ngữ / Định dạng văn bản..."), thanh điều hướng,
tổng đài, danh bạ toà án... — thứ đã lọt vào trích đoạn giáo trình khiến người học đọc không hiểu.

- Lọc theo DÒNG với bộ mẫu chữ ký; chunk sau lọc <200 ký tự → XOÁ (chunks + FTS).
- Chunk sửa nội dung → cập nhật chunks + FTS row (vector hơi lệch chấp nhận được; chunk xoá
  sẽ được loại khỏi FAISS bằng reconstruct như fix_dedup).
- Chạy được cả trên SERVER (chỉ sqlite, không cần faiss: truyền --no-faiss).
"""
import os, re, sqlite3, sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else os.path.join(BASE, "chebien", "nghiep_vu_corpus.db")
NO_FAISS = "--no-faiss" in sys.argv

JUNK_LINE = re.compile(
    r"^(Tình trạng hiệu lực|nh trạng hiệu lực|Hết hiệu lực$|Còn hiệu lực$|Thời gian duy trì hiệu lực|Ngày hết hiệu lực|Ngày có hiệu lực|Ngôn ngữ:|Định dạng văn bản hiện có|Loại văn bản$|Cơ quan ban hành|Người ký$|Số công báo|Nơi ban hành"
    r"|TAND\s|TANDTC$|Tòa án nhân dân (khu vực|tỉnh|TP|huyện|quận|cấp cao)|Cấp giải quyết, xét xử|Sơ thẩm$|Phúc thẩm$|Giám đốc thẩm$|Tái thẩm$|Tội danh\.{0,3}$|Tất cả$"
    r"|Danh mục$|Tổng đài|19006192|0971\.654\.238|Hướng dẫn sử dụng|Liên hệ$|Đăng nhập|Đăng ký|Toggle|Giới thiệu$|Giải pháp$|Bảng giá$|Bài viết$|Trang chủ$|Xem thêm|Tải về|Lưu$|Chia sẻ|In bản án|Đang theo dõi|Theo dõi hiệu lực|©|VietnamLaw|LuatVietnam|Bản án.{0,20}được xem nhiều|Án lệ$|Hợp đồng mẫu|Tra cứu mã HS|Thuật ngữ Pháp lý|email.{0,5}protected"
    r"|Bạn chưa Đăng nhập|Vui lòng Đăng nhập|Đây là tiện ích|Tiện ích dành cho tài khoản|Đã biết\.?$|Quên mật khẩu|Chưa có tài khoản|Đã có [Tt]ài khoản|Điều khoản sử dụng website|Hotline|Zalo\)?$|0971[-. ]?654[-. ]?238|Thông tin dịch vụ$|Dữ liệu pháp lý$|Chính sách và [Hh]ướng|Cho biết trạng thái hiệu lực|Tải về để xem toàn bộ|Tiêu chuẩn$|hoặc Nâng cao\s*\.?$|HOẶC$|Email$|Mật khẩu|Caselaw Việt Nam|Văn bản pháp luật$|Phụ lục đính kèm$|Biểu mẫu$"
    r"|[\wÀ-ỹ .]{0,12}\)$)",
    re.I)
JUNK_ANY = re.compile(r"khu vực \d+\s*[-–]|án nhân dân khu vực|\(TAND[^)]{0,40}\)")

# ── RÁC MỚI PHÁT HIỆN 19/8/2026 khi soi vì sao "Thực hành nghiên cứu hồ sơ" giao nhầm
# mục lục bộ luật cho học viên ─────────────────────────────────────────────────────────
# Mỗi bản án crawl về đều mang theo NGUYÊN TRANG WEB nguồn: form tìm kiếm nâng cao và
# THANH BÊN MỤC LỤC BỘ LUẬT dài 623 dòng ("137.Tội công nhiên chiếm đoạt tài sản (Bộ luật
# hình sự năm 1999)"). Đo trên kho: cả 1.024 bản án đều dính, mỗi bản 623 dòng.
# Hậu quả ở app: đoạn cắt đề bài rơi vào thanh bên đó, học viên chọn lĩnh vực DÂN SỰ lại
# nhận được danh sách tội danh HÌNH SỰ, trong đó có cả bộ luật ĐÃ HẾT HIỆU LỰC.

# Dòng mục lục bộ luật: "137.Tội ..." / "12.Điều ..." — dạng chỉ có ở thanh bên.
MUC_LUC_BO_LUAT = re.compile(r"^\s*\d{1,3}[a-z]?\s*\.\s*(Tội|Điều)\b")

# Mục lục bộ luật khi bị GỘP NHIỀU MỤC TRÊN MỘT DÒNG — dạng "58.Giảm mức hình phạt đã
# tuyên (Bộ luật hình sự năm 1999)". Bắt theo cụm số + tiêu đề + tên bộ luật trong ngoặc,
# vì lúc này mẫu neo đầu dòng không còn ăn. Văn bản bản án bình thường không viết kiểu này.
MUC_LUC_TRONG_DONG = re.compile(
    r"\d{1,3}[a-z]?\s*\.\s*[^.()\n]{3,90}?\s*\((?:Bộ luật|Luật sửa đổi|Luật số)[^)\n]{0,80}\)")

# Form tìm kiếm nâng cao của trang nguồn.
FORM_TIM_KIEM = re.compile(
    r"^(Tìm nâng cao|Tìm kiếm nâng cao|Cụm từ chính xác|Số hiệu văn bản|Ngày ban hành|Ngày cập nhật"
    r"|Tiêu đề|Lĩnh vực|Cơ quan|Loại văn bản|Tình trạng|Sắp xếp|Kết quả tìm kiếm|của tòa án\s*×?)\s*$",
    re.I)

def clean_text(t: str):
    # Bỏ mục lục bộ luật bị gộp trên một dòng TRƯỚC khi lọc theo dòng
    t2 = MUC_LUC_TRONG_DONG.sub(" ", t)
    changed_pre = t2 != t
    t = t2
    out, changed = [], changed_pre
    for line in t.split("\n"):
        st = line.strip()
        if st and (
            JUNK_LINE.match(st)
            or MUC_LUC_BO_LUAT.match(st)
            or FORM_TIM_KIEM.match(st)
            or (len(st) < 130 and JUNK_ANY.search(st))
        ):
            changed = True
            continue
        out.append(line)
    res = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return res, changed

def _run():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=15000")
    cur = con.cursor()
    rows = cur.execute("SELECT id, noi_dung, noi_dung_ctx FROM chunks WHERE chunk_type != 'giai_dap_qa'").fetchall()
    print(f"quét {len(rows)} chunks...", flush=True)
    n_sua = 0
    xoa_ids = []
    batch = 0
    for cid, nd, ctx in rows:
        nd2, ch1 = clean_text(nd or "")
        if not ch1:
            continue
        if len(nd2) < 200:
            xoa_ids.append(cid)
            continue
        header = (ctx or "").split("\n", 1)[0]
        ctx2 = header + "\n" + nd2 if header.startswith("«") else nd2
        cur.execute("UPDATE chunks SET noi_dung=?, noi_dung_ctx=? WHERE id=?", (nd2, ctx2, cid))
        cur.execute("UPDATE chunks_fts SET noi_dung_ctx=? WHERE rowid=?", (ctx2, cid))
        n_sua += 1
        batch += 1
        if batch >= 300:
            con.commit(); batch = 0
    for i in range(0, len(xoa_ids), 400):
        part = xoa_ids[i:i + 400]
        qm = ",".join("?" * len(part))
        cur.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({qm})", part)
        cur.execute(f"DELETE FROM chunks WHERE id IN ({qm})", part)
    con.commit()
    print(f"đã LÀM SẠCH {n_sua} chunks, XOÁ {len(xoa_ids)} chunks toàn rác", flush=True)
    
    if not NO_FAISS and xoa_ids:
        import numpy as np, faiss
        IDX = os.path.join(BASE, "chebien", "nghiep_vu_faiss.index")
        IDMAP = os.path.join(BASE, "chebien", "nghiep_vu_faiss_ids.npy")
        index = faiss.read_index(IDX)
        ids = np.load(IDMAP)
        del_set = set(xoa_ids)
        keep = [i for i, c in enumerate(ids) if int(c) not in del_set]
        new = faiss.IndexFlatIP(index.d)
        B = 20000
        for s0 in range(0, len(keep), B):
            blk = keep[s0:s0 + B]
            new.add(np.vstack([index.reconstruct(int(p)) for p in blk]).astype("float32"))
        faiss.write_index(new, IDX)
        np.save(IDMAP, ids[keep])
        print(f"FAISS còn {new.ntotal} vectors", flush=True)
    print("DONE", flush=True)

if __name__ == "__main__":
    _run()
