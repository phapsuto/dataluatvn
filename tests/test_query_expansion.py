import pytest
import sqlite3
import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.query_expansion import should_expand_query, expand_query, MEMORY_DB

def test_should_expand():
    # Too short
    assert should_expand_query("ly hôn") is False
    assert should_expand_query("đất đai") is False
    # Document symbol
    assert should_expand_query("văn bản số 24/LĐ-NĐ") is False
    assert should_expand_query("nghị định 15/2020/NĐ-CP") is False
    # Valid for expansion
    assert should_expand_query("thủ tục phân chia tài sản sau khi ly hôn") is True
    assert should_expand_query("quy định về xử phạt đua xe máy trái phép") is True

def test_api_and_cache():
    test_q = "quy định về tranh chấp quyền sử dụng đất đai gia đình"
    q_clean = test_q.lower().strip()
    
    # Clean old cache to ensure a fresh test
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM query_expansion_cache WHERE query_text = ?", (q_clean,))
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    # First call: network / FPT Cloud API call
    t1 = time.time()
    terms1 = expand_query(test_q)
    dt1 = time.time() - t1
    
    if terms1:
        assert len(terms1) > 0
        assert len(terms1) <= 3
        
        # Second call: direct SQLite cache read
        t2 = time.time()
        terms2 = expand_query(test_q)
        dt2 = time.time() - t2
        
        assert terms1 == terms2
        assert dt2 < 0.05
