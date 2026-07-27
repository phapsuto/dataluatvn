# tests/test_phase3_universal_tri_tier.py
"""
Kiểm thử tự động Giai đoạn 3: Phổ cập Trải nghiệm Toàn dân trên Web Portal & Telegram Bot.
- Kiểm thử cấu trúc UI/UX trong static/portal.html (Tri-Tier Banner, Selector, NPL Ledger card, DVS badge)
- Kiểm thử lệnh /tier và bộ nhớ chế độ người dùng trong telegram_bot.py
"""

import os
import pytest

from telegram_bot import USER_ACCESS_TIERS, handle_tier_command


def test_portal_html_contains_tritier_ui_elements():
    """Kiểm tra static/portal.html chứa đầy đủ các thành phần Tri-Tier UI/UX."""
    portal_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "portal.html"
    )
    assert os.path.exists(portal_path), "static/portal.html phải tồn tại"

    with open(portal_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. Check CSS & Cards
    assert "tri-tier-selector-banner" in html_content, "Thiếu CSS class tri-tier-selector-banner"
    assert "npl-ledger-card" in html_content, "Thiếu CSS class npl-ledger-card"
    assert "dvs-shield-badge" in html_content, "Thiếu CSS class dvs-shield-badge"

    # 2. Check DOM Elements
    assert 'id="chat-tier-select"' in html_content, "Thiếu thẻ select id=chat-tier-select"
    assert 'value="CITIZEN"' in html_content, "Thiếu value CITIZEN trong tier selector"
    assert 'value="ENTERPRISE"' in html_content, "Thiếu value ENTERPRISE trong tier selector"
    assert 'value="JUDICIAL"' in html_content, "Thiếu value JUDICIAL trong tier selector"

    # 3. Check JS interaction & Payload injection
    assert "function selectTier(" in html_content, "Thiếu hàm JS selectTier"
    assert "access_tier:" in html_content, "Thiếu injection access_tier vào payload sendMessage"


class DummyChat:
    def __init__(self):
        self.messages = []

    def send(self, chat_id, text):
        self.messages.append((chat_id, text))


def test_telegram_bot_tier_command(monkeypatch):
    """Kiểm tra lệnh /tier chuyển đổi chế độ trong Telegram Bot."""
    dummy = DummyChat()

    def dummy_send_message(chat_id, text, **kwargs):
        dummy.send(chat_id, text)
        return {"ok": True}

    import telegram_bot
    monkeypatch.setattr(telegram_bot, "send_message", dummy_send_message)

    chat_id = 99999
    # Test switch to ENTERPRISE
    handle_tier_command(chat_id, "/tier enterprise")
    assert USER_ACCESS_TIERS.get(chat_id) == "ENTERPRISE"
    assert len(dummy.messages) == 1
    assert "ENTERPRISE" in dummy.messages[-1][1]

    # Test switch to JUDICIAL
    handle_tier_command(chat_id, "/tier judicial")
    assert USER_ACCESS_TIERS.get(chat_id) == "JUDICIAL"
    assert len(dummy.messages) == 2
    assert "JUDICIAL" in dummy.messages[-1][1]

    # Test switch to CITIZEN via number
    handle_tier_command(chat_id, "/tier 1")
    assert USER_ACCESS_TIERS.get(chat_id) == "CITIZEN"
    assert len(dummy.messages) == 3
    assert "CITIZEN" in dummy.messages[-1][1]

    # Test invalid argument
    handle_tier_command(chat_id, "/tier unknown_mode")
    assert len(dummy.messages) == 4
    assert "CÚ PHÁP ĐỔI CHẾ ĐỘ PHỔ CẬP" in dummy.messages[-1][1]
