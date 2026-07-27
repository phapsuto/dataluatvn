import pytest
from app.utils.intent_prompts import get_system_prompt_for_tier
from app.utils.blind_spot_engine import BlindSpotFactEngine
from app.utils.normative_ledger import build_npl_from_retrieved_chunks
from app.routers.chatbot import ChatRequest, ChatResponse


def test_get_system_prompt_for_tier_citizen():
    """Kiểm tra system prompt lớp CITIZEN (Dân sinh)."""
    qa_type, prompt = get_system_prompt_for_tier("Xin hỏi quy định chấm dứt hợp đồng", access_tier="CITIZEN")
    assert "CHẾ ĐỘ PHỔ CẬP DÂN SINH" in prompt
    assert "3 BƯỚC HÀNH ĐỘNG" in prompt


def test_get_system_prompt_for_tier_enterprise():
    """Kiểm tra system prompt lớp ENTERPRISE (Doanh nghiệp)."""
    qa_type, prompt = get_system_prompt_for_tier("Xin hỏi quy định chấm dứt hợp đồng", access_tier="ENTERPRISE")
    assert "CHẾ ĐỘ QUẢN TRỊ DOANH NGHIỆP" in prompt
    assert "[CRITICAL]" in prompt or "[MAJOR]" in prompt
    assert "Statutory Conflict Scanner" in prompt


def test_get_system_prompt_for_tier_judicial():
    """Kiểm tra system prompt lớp JUDICIAL (Tư pháp)."""
    qa_type, prompt = get_system_prompt_for_tier("Xin hỏi quy định chấm dứt hợp đồng", access_tier="JUDICIAL")
    assert "CHẾ ĐỘ TÀI PHÁN TƯ PHÁP" in prompt
    assert "TỨ DIỆN RAFA MATRIX" in prompt
    assert "Nghị định 30/2020/NĐ-CP" in prompt


def test_bsfe_blind_spot_detection():
    """Kiểm tra BlindSpotFactEngine nhận diện điểm mù và sinh hướng dẫn phân nhánh."""
    query = "Công ty muốn sa thải lao động nữ mang thai vì thu hẹp sản xuất"
    bsf_list = BlindSpotFactEngine.detect_blind_spots(query)
    assert len(bsf_list) > 0
    
    # Kiểm tra sinh hướng dẫn theo từng tier
    branch_text_citizen = BlindSpotFactEngine.generate_conditional_branching_text(bsf_list, access_tier="CITIZEN")
    assert "3 BƯỚC ANH/CHỊ CẦN CHUẨN BỊ NGAY" in branch_text_citizen
    assert "Trường hợp" in branch_text_citizen or "Quy chế" in branch_text_citizen

    branch_text_judicial = BlindSpotFactEngine.generate_conditional_branching_text(bsf_list, access_tier="JUDICIAL")
    assert "MA TRẬN PHÂN NHÁNH ĐIỀU KIỆN TÀI PHÁN" in branch_text_judicial


def test_npl_dvs_shield_verification():
    """Kiểm tra sổ cái NPL-JSON và chứng thực DVS Shield cho các chunk pháp lý."""
    chunks = [
        {
            "id": 1,
            "title": "Bộ luật Lao động 2019",
            "so_ky_hieu": "45/2019/QH14",
            "text": "Người sử dụng lao động không được sa thải hoặc đơn phương chấm dứt hợp đồng lao động đối với người lao động vì lý do kết hôn, mang thai, nghỉ thai sản.",
            "loai_van_ban": "Luật",
            "tinh_trang_hieu_luc": "Còn hiệu lực"
        }
    ]
    ledger = build_npl_from_retrieved_chunks("Quy định sa thải lao động mang thai", chunks, access_tier="JUDICIAL")
    receipt = ledger.finalize_receipt()
    
    assert receipt["dvs_status"] == "VERIFIED_BY_DVS_SHIELD"
    assert receipt["access_tier"] == "JUDICIAL"
    assert "NPL-" in receipt["receipt_id"]
    assert len(ledger.normative_anchors) == 1
    assert ledger.normative_anchors[0]["sah_tier"] == "TIER_1_BINDING_PRIMARY"
    assert len(ledger.normative_anchors[0]["clf_sha256"]) == 64


def test_chatbot_router_schema_phase2_compat():
    """Kiểm tra tương thích schema ChatRequest và ChatResponse với thuộc tính Phase 2."""
    req = ChatRequest(prompt="Tư vấn hợp đồng", access_tier="ENTERPRISE")
    assert req.access_tier == "ENTERPRISE"
    
    resp = ChatResponse(
        response="Nội dung trả lời",
        citations=[],
        access_tier="ENTERPRISE",
        dvs_status="VERIFIED_BY_DVS_SHIELD",
        npl_payload={"schema_version": "4.0"},
        blind_spots=[{"fact_id": "BSF-01"}]
    )
    assert resp.dvs_status == "VERIFIED_BY_DVS_SHIELD"
    assert resp.npl_payload["schema_version"] == "4.0"
    assert len(resp.blind_spots) == 1
