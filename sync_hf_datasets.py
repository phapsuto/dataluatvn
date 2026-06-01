"""
sync_hf_datasets.py — Kiểm tra & tải incremental từ HuggingFace
So sánh SHA commit → chỉ tải khi tác giả push phiên bản mới.
Chạy hàng tuần qua crontab.
"""
import os
import sys
import json
import time
import sqlite3
import requests

DB_NAME = "vietnamese_legal_documents.db"
LOG_NAME = "logs/sync_hf.log"

HF_DATASETS = [
    {
        "id": "tmquan/phapdien-moj-gov-vn",
        "table": "phapdien_articles",
        "pk": "article_anchor",
        "subset": "articles",
    },
    {
        "id": "tmquan/anle-toaan-gov-vn",
        "table": "anle_documents",
        "pk": "doc_name",
        "subset": "documents",
    },
]


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_NAME), exist_ok=True)
    with open(LOG_NAME, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_remote_sha(dataset_id):
    """Lấy SHA và lastModified mới nhất từ HuggingFace API"""
    url = f"https://huggingface.co/api/datasets/{dataset_id}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            info = r.json()
            return info.get("sha", ""), info.get("lastModified", "")
    except Exception as e:
        log(f"  ⚠️  Lỗi kết nối HF API: {e}")
    return None, None


def get_local_sha(conn, dataset_id):
    """Đọc SHA lần sync cuối từ hf_sync_log"""
    cursor = conn.cursor()
    cursor.execute("SELECT last_sha FROM hf_sync_log WHERE dataset_id = ?", (dataset_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_existing_keys(conn, table, pk):
    """Lấy tập hợp tất cả primary keys đang có trong DB"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT {pk} FROM {table}")
    return set(row[0] for row in cursor.fetchall())


def sync_phapdien_incremental(conn, existing_keys):
    """Import các Điều mới từ phapdien dataset"""
    from datasets import load_dataset

    ds = load_dataset("tmquan/phapdien-moj-gov-vn", "articles", split="train")
    cursor = conn.cursor()
    added = 0

    for row in ds:
        anchor = row.get("article_anchor")
        if anchor in existing_keys:
            continue

        source_links = row.get("source_links")
        source_links_json = None
        if source_links is not None:
            try:
                source_links_json = json.dumps(source_links, ensure_ascii=False)
            except (TypeError, ValueError):
                source_links_json = str(source_links)

        cursor.execute("""
            INSERT OR IGNORE INTO phapdien_articles (
                article_anchor, article_title, chapter_title,
                subject_id, subject_title, topic_id, topic_number, topic_title,
                content_text, content_char_len, content_word_count,
                source_url, source_note_text, source_links_json,
                related_note_text, scraped_at, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            anchor, row.get("article_title"), row.get("chapter_title"),
            row.get("subject_id"), row.get("subject_title"),
            row.get("topic_id"), row.get("topic_number"), row.get("topic_title"),
            row.get("content_text"), row.get("content_char_len"),
            row.get("content_word_count"), row.get("source_url"),
            row.get("source_note_text"), source_links_json,
            row.get("related_note_text"), row.get("scraped_at"), "huggingface",
        ))
        added += 1

    conn.commit()
    return added


def sync_anle_incremental(conn, existing_keys):
    """Import các bản án/án lệ mới từ anle dataset"""
    from datasets import load_dataset
    import math

    ds = load_dataset("tmquan/anle-toaan-gov-vn", "documents", split="train")
    cursor = conn.cursor()
    added = 0

    columns = [
        "doc_name", "title", "doc_code", "doc_type", "case_type",
        "doc_subtype", "year", "issue_date", "issuing_authority",
        "court_level", "jurisdiction", "subject", "markdown",
        "num_pages", "num_sections", "num_paragraphs", "num_sentences",
        "char_len", "text_hash", "precedent_number", "adopted_date",
        "applied_article_code", "applied_article_number",
        "applied_article_clause", "principle_text",
        "detail_url", "pdf_url", "confidence", "parsed_at",
    ]

    for row in ds:
        doc_name = row.get("doc_name")
        if doc_name in existing_keys:
            continue

        values = []
        for col in columns:
            val = row.get(col)
            if val is not None:
                try:
                    if isinstance(val, float) and math.isnan(val):
                        val = None
                except (TypeError, ValueError):
                    pass
            values.append(val)
        values.append("huggingface")

        cursor.execute(f"""
            INSERT OR IGNORE INTO anle_documents (
                {', '.join(columns)}, source
            ) VALUES ({','.join(['?'] * (len(columns) + 1))})
        """, tuple(values))
        added += 1

    conn.commit()
    return added


def update_sync_log(conn, dataset_id, sha, last_modified, added, total):
    """Cập nhật hf_sync_log"""
    cursor = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR REPLACE INTO hf_sync_log
        (dataset_id, last_sha, last_modified, last_checked_at, last_synced_at,
         records_added, records_total)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (dataset_id, sha, last_modified, now, now, added, total))
    conn.commit()


def update_checked_only(conn, dataset_id):
    """Chỉ cập nhật last_checked_at (không có dữ liệu mới)"""
    cursor = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE hf_sync_log SET last_checked_at = ? WHERE dataset_id = ?
    """, (now, dataset_id))
    conn.commit()


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}!")
        sys.exit(1)

    log("=" * 60)
    log("🔄 HUGGINGFACE INCREMENTAL SYNC")
    log("=" * 60)

    conn = sqlite3.connect(DB_NAME)

    for ds_config in HF_DATASETS:
        dataset_id = ds_config["id"]
        table = ds_config["table"]
        pk = ds_config["pk"]

        log(f"\n📦 Kiểm tra: {dataset_id}")

        # 1. Lấy SHA remote
        remote_sha, last_modified = get_remote_sha(dataset_id)
        if remote_sha is None:
            log(f"  ❌ Không kết nối được HF API. Bỏ qua.")
            continue

        # 2. So sánh với SHA local
        local_sha = get_local_sha(conn, dataset_id)
        log(f"  Local SHA:  {(local_sha or 'N/A')[:12]}...")
        log(f"  Remote SHA: {remote_sha[:12]}...")

        if local_sha == remote_sha:
            log(f"  ✅ Không có thay đổi. Bỏ qua.")
            update_checked_only(conn, dataset_id)
            continue

        # 3. Có phiên bản mới → sync incremental
        log(f"  🆕 Phát hiện phiên bản mới! (Modified: {last_modified})")

        existing_keys = get_existing_keys(conn, table, pk)
        log(f"  📊 Đang có {len(existing_keys):,} bản ghi trong DB")

        log(f"  📥 Đang tải và so sánh dữ liệu mới...")
        if "phapdien" in dataset_id:
            added = sync_phapdien_incremental(conn, existing_keys)
        else:
            added = sync_anle_incremental(conn, existing_keys)

        # Đếm tổng sau sync
        cursor = conn.cursor()
        cursor.execute(f"SELECT count(*) FROM {table}")
        total = cursor.fetchone()[0]

        update_sync_log(conn, dataset_id, remote_sha, last_modified, added, total)

        if added > 0:
            log(f"  ✅ Đã thêm {added:,} bản ghi mới! Tổng: {total:,}")
        else:
            log(f"  ✅ Dataset mới nhưng không có bản ghi nào chưa có. Tổng: {total:,}")

    conn.close()
    log("\n🎉 Sync hoàn thành!")


if __name__ == "__main__":
    main()
