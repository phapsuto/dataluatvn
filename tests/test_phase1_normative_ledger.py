"""
test_phase1_normative_ledger.py — Verification tests for DataLuatVN RAG Gen 4 Phase 1
Tests CLF-SHA256 hash invariance, SAH Tier classification, and NPL-JSON schema validity.
"""

import json
import pytest
from app.utils.normative_ledger import (
    clf_sha256_hash,
    determine_sah_tier,
    SAHTier,
    NormativeProofLedger,
    build_npl_from_retrieved_chunks
)


def test_clf_sha256_invariance():
    """Verify CLF-SHA256 generates identical hash for text with different whitespace formatting."""
    text1 = "Người lao động làm việc theo hợp đồng lao động không xác định thời hạn có quyền đơn phương chấm dứt hợp đồng."
    text2 = "  Người lao động  làm việc theo hợp đồng lao động không xác định thời hạn   có quyền đơn phương chấm dứt hợp đồng.  \n"
    
    hash1 = clf_sha256_hash(text1)
    hash2 = clf_sha256_hash(text2)
    assert hash1 == hash2, "CLF-SHA256 must normalize whitespace and case deterministically!"
    assert len(hash1) == 64, "CLF-SHA256 must return a 64-character hex digest"
    print(f"✅ CLF-SHA256 invariance test PASSED -> hash: {hash1[:16]}...")


def test_sah_tier_classification():
    """Verify Statutory Authority Hierarchy (SAH Tier 1 to 4) classification."""
    assert determine_sah_tier("45/2019/QH14", "Luật", "Quốc hội", "Bộ luật Lao động 2019") == SAHTier.TIER_1_BINDING_PRIMARY
    assert determine_sah_tier("01/2020/AL", "Quyết định", "TANDTC", "Án lệ số 01/2020/AL về vụ án lao động") == SAHTier.TIER_2_JUDICIAL_PRECEDENT
    assert determine_sah_tier("1234/LĐTBXH-QHLĐ", "Công văn", "Bộ LĐTBXH", "Hướng dẫn thực hiện Nghị định 145") == SAHTier.TIER_3_EXPERT_GUIDANCE
    assert determine_sah_tier("", "Bài viết", "", "Tham khảo bình luận pháp luật lao động") == SAHTier.TIER_4_INFORMAL_REFERENCE
    print("✅ SAH Hierarchy classification test PASSED")


def test_npl_json_ledger_builder():
    """Verify Normative Proof Ledger builder correctly generates npl-v1.json payload."""
    ledger = NormativeProofLedger(
        query="Đơn phương chấm dứt hợp đồng lao động báo trước mấy ngày?",
        access_tier="ENTERPRISE"
    )
    anchor_id = ledger.add_anchor(
        doc_symbol="45/2019/QH14",
        article="Điều 35",
        clause="Khoản 1",
        content_snippet="Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước...",
        doc_type="Luật",
        issuer="Quốc hội",
        title="Bộ luật Lao động"
    )
    assert anchor_id == "NA-01"
    
    ledger.add_proposition(
        prop_id="P-01",
        statement="Người lao động được đơn phương chấm dứt hợp đồng tuân thủ thời hạn báo trước quy định tại Điều 35.",
        supporting_anchors=["NA-01"],
        confidence=0.99
    )
    
    receipt = ledger.finalize_receipt()
    assert receipt["dvs_status"] == "VERIFIED_BY_DVS_SHIELD"
    assert receipt["tier1_primary_count"] == 1
    assert receipt["hash_integrity_check"] == "PASSED"
    
    payload_json = ledger.to_json()
    parsed = json.loads(payload_json)
    assert parsed["schema_version"] == "1.0-RAG-GEN4"
    assert parsed["access_tier"] == "ENTERPRISE"
    assert len(parsed["normative_anchors"]) == 1
    print("✅ NPL-JSON Ledger Builder & Receipt verification PASSED")


def test_build_npl_from_retrieved_chunks():
    """Verify helper build_npl_from_retrieved_chunks converts search results to NPL ledger."""
    mock_chunks = [
        {
            "so_ky_hieu": "45/2019/QH14",
            "dieu_luat": "Điều 36",
            "khoan_luat": "Khoản 1",
            "text": "Người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng lao động trong trường hợp người lao động thường xuyên không hoàn thành công việc theo hợp đồng lao động.",
            "loai_vb": "Luật",
            "co_quan_ban_hanh": "Quốc hội",
            "title": "Bộ luật Lao động"
        }
    ]
    ledger = build_npl_from_retrieved_chunks(
        query="Công ty đuổi việc do không hoàn thành công việc",
        chunks=mock_chunks,
        access_tier="JUDICIAL"
    )
    data = ledger.to_dict()
    assert len(data["normative_anchors"]) == 1
    assert data["normative_anchors"][0]["sah_tier"] == SAHTier.TIER_1_BINDING_PRIMARY
    assert data["audit_receipt"]["dvs_status"] == "VERIFIED_BY_DVS_SHIELD"
    print("✅ build_npl_from_retrieved_chunks test PASSED")


if __name__ == "__main__":
    test_clf_sha256_invariance()
    test_sah_tier_classification()
    test_npl_json_ledger_builder()
    test_build_npl_from_retrieved_chunks()
    print("\n🎉 ALL PHASE 1 NORMATIVE LEDGER TESTS PASSED SUCCESSFULLY!")
