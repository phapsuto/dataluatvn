import pytest
import sqlite3
import time
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import app

API_KEY = "dlvn_testkey"
MAIN_DB = "vietnamese_legal_documents.db"

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

@pytest.fixture(scope="module")
def sample_doc():
    conn = sqlite3.connect(MAIN_DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc, d.title
        FROM documents d
        JOIN document_chunks c ON d.id = c.doc_id
        WHERE d.so_ky_hieu IS NOT NULL AND d.so_ky_hieu != '' AND d.so_ky_hieu != 'N/A'
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row

def test_metadata_filtering(client, sample_doc):
    if not sample_doc:
        pytest.skip("No sample document found in DB")
    so_ky_hieu, loai_van_ban, status, title = sample_doc
    
    headers = {"X-API-Key": API_KEY}
    response = client.get(
        f"/laws/smart-search?q=quy+định+về+xử+phạt&loai_van_ban={loai_van_ban}&limit=5",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", [])
    
    for item in results:
        assert item.get("document_loai_van_ban") == loai_van_ban

def test_symbol_boosting(client, sample_doc):
    if not sample_doc:
        pytest.skip("No sample document found in DB")
    so_ky_hieu, loai_van_ban, status, title = sample_doc
    
    headers = {"X-API-Key": API_KEY}
    test_query = f"Nội dung quy định trong văn bản số {so_ky_hieu}"
    response = client.get(
        f"/laws/smart-search?q={test_query}&limit=5",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", [])
    
    if results:
        top_item = results[0]
        top_symbol = top_item.get("document_so_ky_hieu")
        top_score = top_item.get("score", 0.0)
        
        clean_sample = so_ky_hieu.replace(" ", "").lower()
        clean_top = top_symbol.replace(" ", "").lower()
        
        assert clean_sample in clean_top
        assert top_score >= 1.5

def test_status_boosting(client):
    headers = {"X-API-Key": API_KEY}
    response = client.get(
        "/laws/smart-search?q=quy+định+pháp+luật&limit=5",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", [])
    if results:
        assert "score" in results[0]

def test_semantic_reranking(client):
    headers = {"X-API-Key": API_KEY}
    query = "quy định xử phạt hành chính đối với hành vi đua xe máy"
    
    # Warm-up call
    client.get(f"/laws/smart-search?q={query}&limit=5", headers=headers)
    
    response = client.get(
        f"/laws/smart-search?q={query}&limit=5",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", [])
    
    if results:
        top_item = results[0]
        top_score = top_item.get("score", 0.0)
        # Verify reranker added similarity score (RRF max is 0.033, so if similarity boost is active it should be > 0.5)
        assert top_score > 0.5
