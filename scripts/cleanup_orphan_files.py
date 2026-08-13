import os
import sqlite3
import shutil

# Đường dẫn (phải chạy từ thư mục gốc dataluatvn)
DATA_DIR = "data"
NOTEBOOK_DB = os.path.join(DATA_DIR, "notebooks.db")
FAISS_DIR = os.path.join(DATA_DIR, "notebooks_faiss")
UPLOADS_DIR = os.path.join(DATA_DIR, "notebooks_uploads")

def cleanup():
    if not os.path.exists(NOTEBOOK_DB):
        print("Không tìm thấy DB:", NOTEBOOK_DB)
        return

    conn = sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()

    # 1. Lấy danh sách ID của tất cả Notebooks đang tồn tại
    c.execute("SELECT id FROM notebooks")
    valid_notebooks = set([r[0] for r in c.fetchall()])
    print(f"Có {len(valid_notebooks)} sổ tay hợp lệ trong DB.")

    # 2. Quét thư mục FAISS
    if os.path.exists(FAISS_DIR):
        faiss_dirs = os.listdir(FAISS_DIR)
        removed_faiss = 0
        for fd in faiss_dirs:
            # fd chính là notebook_id
            if fd not in valid_notebooks:
                path = os.path.join(FAISS_DIR, fd)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    removed_faiss += 1
        print(f"Đã xoá {removed_faiss} thư mục FAISS mồ côi.")

    # 3. Lấy danh sách ID của tất cả Sources đang tồn tại
    c.execute("SELECT id FROM notebook_sources")
    valid_sources = set([r[0] for r in c.fetchall()])
    print(f"Có {len(valid_sources)} tài liệu (sources) hợp lệ trong DB.")

    # 4. Quét thư mục Uploads
    if os.path.exists(UPLOADS_DIR):
        upload_files = os.listdir(UPLOADS_DIR)
        removed_uploads = 0
        freed_bytes = 0
        for uf in upload_files:
            # Tên file thường là source_id hoặc source_id + ext
            source_id = uf.split('.')[0]
            if source_id not in valid_sources:
                path = os.path.join(UPLOADS_DIR, uf)
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    os.remove(path)
                    removed_uploads += 1
                    freed_bytes += size
        
        print(f"Đã xoá {removed_uploads} file PDF/Docx mồ côi. Giải phóng {freed_bytes / (1024*1024):.2f} MB.")

    conn.close()
    print("Hoàn tất dọn rác!")

if __name__ == "__main__":
    cleanup()
