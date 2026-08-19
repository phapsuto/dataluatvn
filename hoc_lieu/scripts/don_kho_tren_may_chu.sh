#!/usr/bin/env bash
# DỌN KHO NGHIỆP VỤ TRÊN MÁY CHỦ — chạy một lệnh, đủ cả sao lưu và kiểm chứng.
#
# Vì sao có tệp này: đợt 19/8/2026 tìm ra hai lỗi dữ liệu ở khâu nạp kho (bản án dính
# nguyên giao diện trang nguồn; 57% tài liệu gắn nhãn BẢN ÁN thật ra là QUYẾT ĐỊNH).
# Bốn script sửa phải chạy ĐÚNG THỨ TỰ, và bước cuối — đồng bộ FAISS — là bắt buộc:
# ba bước đầu xoá chunk trong SQLite mà không đụng chỉ mục, để lệch thì tìm kiếm ngữ
# nghĩa trả về id không còn tồn tại, người dùng nhận kết quả rỗng mà nhìn chỉ mục vẫn
# thấy "đủ vector" nên rất khó lần ra.
#
# CÁCH DÙNG trên máy chủ:
#     cd /home/dataluat/dataluatvn
#     bash hoc_lieu/scripts/don_kho_tren_may_chu.sh --thu    # chỉ đếm, không sửa gì
#     bash hoc_lieu/scripts/don_kho_tren_may_chu.sh          # làm thật
#
# Làm thật sẽ: sao lưu 3 tệp kho → chạy 4 script → khởi động lại dịch vụ → kiểm chứng.
# Có bất kỳ bước nào hỏng là dừng ngay (set -e), bản sao lưu vẫn còn nguyên để lùi lại.

set -euo pipefail

CHI_THU=0
[ "${1:-}" = "--thu" ] && CHI_THU=1

GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Đường dẫn kho KHÁC NHAU giữa máy lập trình và máy chủ: ở máy là hoc_lieu/chebien/,
# trên máy chủ lại nằm thẳng ở thư mục gốc dự án. Tự dò thay vì bắt người chạy nhớ.
DB=""
for thu in "$GOC/hoc_lieu/chebien/nghiep_vu_corpus.db" "$GOC/nghiep_vu_corpus.db" "./nghiep_vu_corpus.db"; do
  [ -f "$thu" ] && { DB="$(cd "$(dirname "$thu")" && pwd)/$(basename "$thu")"; break; }
done
[ -n "$DB" ] || { echo "KHÔNG TÌM THẤY nghiep_vu_corpus.db — chạy lại kèm: --db <đường dẫn>"; exit 1; }
CHEBIEN="$(dirname "$DB")"
IDX="$CHEBIEN/nghiep_vu_faiss.index"
IDS="$CHEBIEN/nghiep_vu_faiss_ids.npy"
HAU_TO="truoc-khi-don-$(date +%Y%m%d-%H%M%S)"

echo "== KHO: $CHEBIEN"
[ -f "$DB" ] || { echo "THIẾU TỆP: $DB"; exit 1; }
for f in "$IDX" "$IDS"; do
  [ -f "$f" ] || { echo "THIẾU CHỈ MỤC: $f"; echo "   (dọn SQLite mà không đồng bộ được FAISS là hỏng tìm kiếm — dừng)"; exit 1; }
done
df -h "$CHEBIEN" | tail -1

echo
echo "== BƯỚC 0 — chạy thử, chỉ đếm =="
python3 "$GOC/hoc_lieu/scripts/cat_dau_trang_ban_an.py"    --db "$DB" --thu
python3 "$GOC/hoc_lieu/scripts/gan_lai_nhan_quyet_dinh.py" --db "$DB" --thu
python3 "$GOC/hoc_lieu/scripts/dong_bo_faiss_theo_sqlite.py" --db "$DB" --index "$IDX" --thu

if [ "$CHI_THU" = "1" ]; then
  echo
  echo "== CHỈ CHẠY THỬ — chưa sửa gì. Bỏ cờ --thu để làm thật. =="
  exit 0
fi

echo
echo "== BƯỚC 1 — sao lưu =="
for f in "$DB" "$IDX" "$IDS"; do
  cp -p "$f" "$f.$HAU_TO"
  echo "   $(basename "$f").$HAU_TO  ($(du -h "$f.$HAU_TO" | cut -f1))"
done

echo
echo "== BƯỚC 2 — dọn, ĐÚNG THỨ TỰ =="
python3 "$GOC/hoc_lieu/scripts/cat_dau_trang_ban_an.py"      --db "$DB"
python3 "$GOC/hoc_lieu/scripts/gan_lai_nhan_quyet_dinh.py"   --db "$DB"
python3 "$GOC/hoc_lieu/scripts/clean_corpus_junk.py"         --db "$DB" --no-faiss
python3 "$GOC/hoc_lieu/scripts/dong_bo_faiss_theo_sqlite.py" --db "$DB" --index "$IDX"

echo
echo "== BƯỚC 3 — đếm lại =="
python3 - "$DB" "$IDS" <<'PY'
import sqlite3, sys
import numpy as np
db, ids_path = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
chunk = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
ban_an = con.execute("SELECT COUNT(*) FROM docs WHERE loai_tai_lieu='BAN_AN'").fetchone()[0]
quyet_dinh = con.execute("SELECT COUNT(*) FROM docs WHERE loai_tai_lieu='QUYET_DINH'").fetchone()[0]
song = set(r[0] for r in con.execute("SELECT id FROM chunks"))
ids = np.load(ids_path)
mo_coi = sum(1 for i in ids if int(i) not in song)
print(f"   chunk: {chunk} | bản án: {ban_an} | quyết định: {quyet_dinh}")
print(f"   vector FAISS: {len(ids)} | mồ côi: {mo_coi}  (phải = 0)")
if mo_coi:
    raise SystemExit("CHỈ MỤC CÒN LỆCH — dừng lại, xem lại bước đồng bộ FAISS")
PY

echo
echo "== BƯỚC 4 — khởi động lại dịch vụ =="
systemctl restart dataluat-api
sleep 6
systemctl is-active dataluat-api
echo "   PID giữ cổng 2004 (phải trùng MainPID bên dưới):"
ss -ltnp 2>/dev/null | grep ':2004' || true
systemctl show -p MainPID dataluat-api

echo
echo "== BƯỚC 5 — gọi thử kho =="
curl -s -o /dev/null -w "   api-law-v3 ngoài: HTTP %{http_code}\n" https://api-law-v3.vincode.xyz/ || true
echo
echo "XONG. Bản sao lưu mang hậu tố .$HAU_TO — chỉ xoá khi đã dùng thật thấy ổn."
