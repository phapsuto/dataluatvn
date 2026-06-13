#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🤖 LuatBot Telegram — Trợ lý Pháp lý AI trên Telegram            ║
║  Tích hợp với hệ thống RAG 7 Tầng của LuatBot API                 ║
╚══════════════════════════════════════════════════════════════════════╝

Cách chạy:
    python3 telegram_bot.py

Yêu cầu:
    pip install python-telegram-bot requests

Biến môi trường (tùy chọn):
    TELEGRAM_BOT_TOKEN    — Token từ BotFather (mặc định đã cấu hình)
    LUATBOT_API_URL       — URL API LuatBot (mặc định: http://localhost:2004)
    LUATBOT_API_KEY       — API Key cho LuatBot (mặc định: dlvn_testkey)
"""

import os
import sys
import json
import time
import logging
import html
import textwrap
import threading
import subprocess
from datetime import datetime
from typing import Optional

import requests


# ══════════════════════════════════════════════════
# CẤU HÌNH
# ══════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "7660859485:AAFiyYQF7sh3nSp0dkYNFMo8-31LPyj7RRA"
)

LUATBOT_API_URL = os.environ.get("LUATBOT_API_URL", "http://localhost:2004")
LUATBOT_API_KEY = os.environ.get("LUATBOT_API_KEY", "dlvn_testkey")

# Danh sách Telegram user_id được phép dùng bot (để trống = ai cũng dùng được)
ALLOWED_USER_IDS = []  # Ví dụ: [123456789, 987654321]

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 10
user_request_timestamps = {}

# Logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/telegram_bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
# TELEGRAM API HELPERS (Pure HTTP — không cần thư viện phức tạp)
# ══════════════════════════════════════════════════

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def tg_request(method: str, data: dict = None, timeout: float = 30.0) -> dict:
    """Gọi Telegram Bot API."""
    url = f"{TELEGRAM_API}/{method}"
    try:
        resp = requests.post(url, json=data, timeout=timeout)
        result = resp.json()
        if not result.get("ok"):
            logger.error(f"Telegram API error: {result}")
        return result
    except Exception as e:
        logger.error(f"Telegram API request failed: {e}")
        return {"ok": False, "error": str(e)}


def md_to_html(text: str) -> str:
    """Chuyển đổi Telegram Markdown V1 sang HTML."""
    import re
    import html
    
    # 1. Escape HTML special characters
    text = html.escape(text, quote=False)
    
    # 2. Convert code blocks: ```lang ... ``` or ``` ... ```
    text = re.sub(r'```(?:\w+)?\n(.*?)\n```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # 3. Convert inline code: `code`
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    
    # 4. Convert bold: **text** hoặc *text*
    text = re.sub(r'\*\*([^*<\n]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*([^*<\n]+)\*', r'<b>\1</b>', text)
    
    # 5. Convert italic: _text_
    text = re.sub(r'_([^_<\n]+)_', r'<i>\1</i>', text)
    
    return text


def send_message(chat_id: int, text: str, parse_mode: str = "HTML",
                 reply_to: int = None, disable_preview: bool = True) -> dict:
    """Gửi tin nhắn Telegram với HTML hoặc Plain text."""
    if parse_mode == "HTML":
        text = md_to_html(text)
        
    # Telegram giới hạn 4096 ký tự / tin nhắn
    if len(text) > 4000:
        # Chia tin nhắn thành nhiều phần
        parts = split_message(text, 4000)
        result = None
        for part in parts:
            payload = {
                "chat_id": chat_id,
                "text": part,
                "reply_to_message_id": reply_to,
                "disable_web_page_preview": disable_preview,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            result = tg_request("sendMessage", payload)
        return result
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to,
        "disable_web_page_preview": disable_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return tg_request("sendMessage", payload)


def send_typing(chat_id: int):
    """Hiển thị trạng thái 'đang gõ...' cho user."""
    tg_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})


def split_message(text: str, max_len: int = 4000) -> list:
    """Chia tin nhắn dài thành nhiều phần nhỏ."""
    if len(text) <= max_len:
        return [text]
    
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        
        # Tìm điểm xuống dòng gần nhất trước giới hạn
        split_pos = text.rfind("\n", 0, max_len)
        if split_pos == -1:
            split_pos = text.rfind(". ", 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    
    return parts


# ══════════════════════════════════════════════════
# LUATBOT API CLIENT
# ══════════════════════════════════════════════════

def call_luatbot_chat(prompt: str, session_id: str = "telegram_default") -> dict:
    """Gọi API /assistant/chat của LuatBot."""
    url = f"{LUATBOT_API_URL}/assistant/chat"
    headers = {
        "X-API-Key": LUATBOT_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "session_id": f"telegram_{session_id}",
    }
    
    try:
        start = time.time()
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        latency = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            data["_latency"] = round(latency, 2)
            return data
        else:
            return {
                "error": True,
                "status_code": resp.status_code,
                "detail": resp.text[:500],
            }
    except requests.ConnectionError:
        return {
            "error": True,
            "detail": "❌ Không thể kết nối tới LuatBot API server.\n"
                      f"Server: {LUATBOT_API_URL}\n"
                      "Hãy chắc chắn server đang chạy: `python3 server.py`"
        }
    except requests.Timeout:
        return {"error": True, "detail": "⏰ Timeout — server phản hồi quá chậm (>120s)."}
    except Exception as e:
        return {"error": True, "detail": f"Lỗi không xác định: {str(e)}"}


def call_luatbot_search(query: str, limit: int = 5) -> dict:
    """Gọi API /laws/smart-search của LuatBot."""
    url = f"{LUATBOT_API_URL}/laws/smart-search"
    headers = {"X-API-Key": LUATBOT_API_KEY}
    params = {"q": query, "limit": limit}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        return {"error": True, "detail": f"HTTP {resp.status_code}"}
    except requests.ConnectionError:
        return {"error": True, "detail": "❌ Server chưa chạy."}
    except Exception as e:
        return {"error": True, "detail": str(e)}


def check_server_health() -> dict:
    """Kiểm tra trạng thái server LuatBot."""
    try:
        resp = requests.get(f"{LUATBOT_API_URL}/", timeout=5)
        if resp.status_code == 200:
            return {"online": True, "data": resp.json()}
        return {"online": False, "detail": f"HTTP {resp.status_code}"}
    except:
        return {"online": False, "detail": "Connection refused"}


# ══════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════

def check_rate_limit(user_id: int) -> bool:
    """Kiểm tra rate limit. Trả về True nếu ok, False nếu bị giới hạn."""
    now = time.time()
    if user_id not in user_request_timestamps:
        user_request_timestamps[user_id] = []
    
    # Xóa các timestamp cũ hơn 60 giây
    user_request_timestamps[user_id] = [
        ts for ts in user_request_timestamps[user_id] if now - ts < 60
    ]
    
    if len(user_request_timestamps[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    user_request_timestamps[user_id].append(now)
    return True


# ══════════════════════════════════════════════════
# FORMAT RESPONSE
# ══════════════════════════════════════════════════

def format_chat_response(data: dict) -> str:
    """Format kết quả /assistant/chat thành Markdown đẹp cho Telegram."""
    if data.get("error"):
        return f"⚠️ *Lỗi:*\n{data.get('detail', 'Unknown error')}"
    
    response = data.get("response", "Không có phản hồi.")
    domain = data.get("domain", "")
    citations = data.get("citations", [])
    flare = data.get("flare_activated", False)
    latency = data.get("_latency", 0)
    
    # Header theo domain
    domain_icons = {
        "chitchat": "💬",
        "lao_dong": "👷",
        "dan_su": "📋",
        "hinh_su": "⚖️",
        "dat_dai": "🏘️",
        "doanh_nghiep": "🏢",
        "hanh_chinh": "📜",
        "cached": "🎯",
        "out_of_scope": "🛑",
    }
    icon = domain_icons.get(domain, "⚖️")
    
    parts = [f"{icon} *LuatBot*\n"]
    parts.append(response)
    
    # Citations
    if citations:
        parts.append("\n\n📎 *Trích dẫn:*")
        for i, cite in enumerate(citations[:5], 1):
            title = cite.get("title", "N/A")
            so_ky_hieu = cite.get("so_ky_hieu", "")
            status = cite.get("tinh_trang_hieu_luc", "")
            status_emoji = "🟢" if "hiệu lực" in (status or "").lower() else "⚪"
            
            cite_line = f"{i}. {status_emoji} {title}"
            if so_ky_hieu:
                cite_line += f" ({so_ky_hieu})"
            parts.append(cite_line)
    
    # Footer
    footer_items = []
    if latency:
        footer_items.append(f"⏱️{latency}s")
    if domain and domain not in ["chitchat", "out_of_scope"]:
        footer_items.append(f"📂{domain}")
    if flare:
        footer_items.append("🔄FLARE")
    if footer_items:
        parts.append(f"\n_{' · '.join(footer_items)}_")
    
    return "\n".join(parts)


def format_search_results(data: dict, query: str) -> str:
    """Format kết quả /laws/smart-search."""
    if data.get("error"):
        return f"⚠️ *Lỗi tìm kiếm:*\n{data.get('detail', 'Unknown')}"
    
    results = data if isinstance(data, list) else data.get("results", data.get("items", []))
    
    if not results:
        return f"🔍 Không tìm thấy kết quả cho: _{query}_"
    
    parts = [f"🔍 *Kết quả tìm kiếm:* _{query}_\n"]
    
    for i, doc in enumerate(results[:5], 1):
        title = doc.get("title", "N/A")
        so_ky_hieu = doc.get("so_ky_hieu", "")
        loai = doc.get("loai_van_ban", "")
        status = doc.get("tinh_trang_hieu_luc", "")
        score = doc.get("score", 0)
        
        status_emoji = "🟢" if "hiệu lực" in (status or "").lower() else "⚪"
        
        parts.append(
            f"*{i}.* {status_emoji} {title}\n"
            f"   📝 {loai} | {so_ky_hieu}\n"
            f"   📊 Score: {score:.2f}" if score else
            f"*{i}.* {status_emoji} {title}\n"
            f"   📝 {loai} | {so_ky_hieu}"
        )
    
    return "\n".join(parts)


# ══════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════

def handle_start(chat_id: int, user_name: str):
    """Xử lý lệnh /start."""
    welcome = (
        "⚖️ *Chào mừng đến với LuatBot!*\n\n"
        f"Xin chào *{user_name}*! Tôi là Trợ lý Pháp lý AI "
        "chuyên sâu về luật Việt Nam, được trang bị hệ thống RAG 7 Tầng.\n\n"
        "🔹 *Gõ câu hỏi trực tiếp* — Tôi sẽ trả lời với trích dẫn điều khoản\n"
        "🔹 `/search [từ khóa]` — Tìm kiếm văn bản pháp luật\n"
        "🔹 `/status` — Kiểm tra trạng thái server\n"
        "🔹 `/help` — Xem hướng dẫn chi tiết\n\n"
        "💡 *Ví dụ:*\n"
        "_Thời gian nghỉ thai sản theo luật lao động?_\n"
        "_Điều kiện thành lập công ty TNHH?_\n"
        "_So sánh tội trộm cắp và cướp tài sản?_"
    )
    send_message(chat_id, welcome)


def handle_help(chat_id: int):
    """Xử lý lệnh /help."""
    help_text = (
        "📖 *Hướng dẫn sử dụng LuatBot*\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💬 *Chat trực tiếp*\n"
        "Gõ bất kỳ câu hỏi pháp luật nào, bot sẽ:\n"
        "• Phân tích ý định (Semantic Router)\n"
        "• Truy xuất văn bản liên quan (RAG)\n"
        "• Trả lời kèm trích dẫn điều khoản\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔍 *Lệnh tìm kiếm*\n"
        "`/search luật lao động 2019` — Tìm văn bản\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💻 *Lệnh điều khiển IDE Agent*\n"
        "`/agent [lệnh]` — Ra lệnh trực tiếp cho AI Agent trong IDE\n"
        "Ví dụ: `/agent viết test case cho chatbot.py`\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *Lệnh hệ thống*\n"
        "`/status` — Trạng thái server & API\n"
        "`/benchmark` — Kết quả benchmark gần nhất\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Mẹo*\n"
        "• Hỏi chi tiết = câu trả lời tốt hơn\n"
        "• Bot nhớ ngữ cảnh theo session\n"
        "• Hỗ trợ: Lao động, Dân sự, Hình sự,\n"
        "  Đất đai, Doanh nghiệp, Hành chính"
    )
    send_message(chat_id, help_text)


def handle_status(chat_id: int):
    """Xử lý lệnh /status."""
    send_typing(chat_id)
    
    health = check_server_health()
    
    if health["online"]:
        data = health.get("data", {})
        total_docs = data.get("total_documents_loaded") or data.get("total_documents", "N/A")
        if isinstance(total_docs, (int, float)):
            docs_str = f"{total_docs:,}"
        else:
            docs_str = str(total_docs)
            
        msg = (
            "🟢 *LuatBot Server — ONLINE*\n\n"
            f"📡 URL: `{LUATBOT_API_URL}`\n"
            f"📊 Status: {data.get('status', 'ok')}\n"
            f"📚 Documents: {docs_str}\n"
            f"⏰ Checked: {datetime.now().strftime('%H:%M:%S')}"
        )
    else:
        msg = (
            "🔴 *LuatBot Server — OFFLINE*\n\n"
            f"📡 URL: `{LUATBOT_API_URL}`\n"
            f"❌ {health.get('detail', 'Connection refused')}\n\n"
            "💡 Khởi chạy server:\n"
            "`cd luatvietnam && python3 server.py`"
        )
    
    send_message(chat_id, msg)


def handle_benchmark(chat_id: int):
    """Xử lý lệnh /benchmark — gửi kết quả benchmark gần nhất."""
    send_typing(chat_id)
    
    benchmark_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scratch", "benchmark_llm_results.json"
    )
    
    if not os.path.exists(benchmark_file):
        send_message(chat_id, "⚠️ Chưa có kết quả benchmark.\nChạy: `python3 scratch/benchmark_llm_models.py`")
        return
    
    try:
        with open(benchmark_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        summary = data.get("summary", {})
        ts = data.get("timestamp", "N/A")
        
        parts = [
            f"📊 *Benchmark LLM Models*\n📅 _{ts[:19]}_\n",
            "━━━━━━━━━━━━━━━━━━\n"
        ]
        
        # Sort by score
        sorted_models = sorted(summary.items(), key=lambda x: x[1]["avg_score"], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (model_key, stats) in enumerate(sorted_models):
            medal = medals[i] if i < 3 else f"#{i+1}"
            parts.append(
                f"{medal} *{stats['name']}*\n"
                f"   📈 Score: *{stats['avg_score']}%*\n"
                f"   ⏱️ Latency: {stats['avg_latency']}s\n"
                f"   🔢 Tokens: {stats['avg_tokens']:.0f}\n"
                f"   ⚠️ Ảo giác: {stats['hallucination_count']}\n"
            )
        
        send_message(chat_id, "\n".join(parts))
    except Exception as e:
        send_message(chat_id, f"⚠️ Lỗi đọc benchmark: {str(e)}")


def handle_search(chat_id: int, query: str):
    """Xử lý lệnh /search."""
    if not query.strip():
        send_message(chat_id, "🔍 Cú pháp: `/search [từ khóa]`\nVí dụ: `/search luật lao động 2019`")
        return
    
    send_typing(chat_id)
    result = call_luatbot_search(query)
    msg = format_search_results(result, query)
    send_message(chat_id, msg)


def handle_chat(chat_id: int, user_id: int, text: str, message_id: int):
    """Xử lý chat pháp luật trực tiếp."""
    send_typing(chat_id)
    
    result = call_luatbot_chat(text, session_id=str(user_id))
    
    msg = format_chat_response(result)
    
    # Fallback nếu HTML bị lỗi
    resp = send_message(chat_id, msg, parse_mode="HTML", reply_to=message_id)
    if not resp.get("ok"):
        # Thử lại không định dạng
        plain_msg = msg.replace("*", "").replace("_", "").replace("`", "")
        send_message(chat_id, plain_msg, parse_mode=None, reply_to=message_id)


# ══════════════════════════════════════════════════
# TELEGRAM <-> IDE AGENT SYNC CONFIGURATION
# ══════════════════════════════════════════════════

SYNC_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".telegram_sync.json"
)

active_continuous_polls = {}
stop_events = {}
last_sent_from_telegram = {}

def load_sync_config() -> dict:
    """Đọc cấu hình đồng bộ từ file."""
    if os.path.exists(SYNC_CONFIG_FILE):
        try:
            with open(SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Lỗi đọc file sync config: {e}")
    return {}

def save_sync_config(config: dict):
    """Ghi cấu hình đồng bộ xuống file."""
    try:
        with open(SYNC_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Lỗi ghi file sync config: {e}")

def get_sync_chat_id() -> Optional[int]:
    """Lấy chat_id đang được bật đồng bộ."""
    config = load_sync_config()
    if config.get("sync_enabled"):
        return config.get("chat_id")
    return None

def is_sync_enabled(chat_id: int) -> bool:
    """Kiểm tra xem chat_id này có đang được đồng bộ không."""
    config = load_sync_config()
    return config.get("sync_enabled", False) and config.get("chat_id") == chat_id

def start_continuous_polling(chat_id: int):
    """Bắt đầu thread polling liên tục cho chat_id."""
    if chat_id in active_continuous_polls:
        thread = active_continuous_polls[chat_id]
        if thread.is_alive():
            logger.info(f"Thread continuous polling cho chat {chat_id} đang chạy rồi.")
            return
            
    logger.info(f"Khởi chạy thread continuous polling mới cho chat {chat_id}")
    stop_event = threading.Event()
    stop_events[chat_id] = stop_event
    stop_event.clear()
    
    thread = threading.Thread(
        target=poll_agent_continuous_loop,
        args=(chat_id, stop_event),
        daemon=True
    )
    active_continuous_polls[chat_id] = thread
    thread.start()

def stop_continuous_polling(chat_id: int):
    """Dừng thread polling liên tục cho chat_id."""
    if chat_id in stop_events:
        logger.info(f"Dừng thread continuous polling cho chat {chat_id}")
        stop_events[chat_id].set()
        stop_events.pop(chat_id, None)
        active_continuous_polls.pop(chat_id, None)

def poll_agent_continuous_loop(chat_id: int, stop_event: threading.Event):
    """Vòng lặp poll liên tục transcript của conversation hiện tại."""
    logger.info(f"Bắt đầu vòng lặp poll continuous cho chat_id {chat_id}")
    
    last_conv_id = None
    last_idx = 0
    
    # Khởi tạo last_idx từ conversation hiện tại
    current_conv_id = get_current_conversation_id()
    if current_conv_id:
        last_conv_id = current_conv_id
        last_idx = get_latest_step_index(current_conv_id)
        logger.info(f"Khởi tạo continuous poll cho conv {current_conv_id} tại step {last_idx}")
        
    while not stop_event.is_set():
        current_conv_id = get_current_conversation_id()
        if not current_conv_id:
            time.sleep(2)
            continue
            
        # Nếu đổi sang conversation mới
        if current_conv_id != last_conv_id:
            last_conv_id = current_conv_id
            last_idx = get_latest_step_index(current_conv_id)
            send_message(
                chat_id, 
                f"🔄 *Đã tự động chuyển đồng bộ sang Conversation mới:*\n`{current_conv_id}`"
            )
            logger.info(f"Chuyển continuous poll sang conv {current_conv_id} tại step {last_idx}")
            
        transcript_path = f"/Users/tonguyen/.gemini/antigravity-ide/brain/{current_conv_id}/.system_generated/logs/transcript.jsonl"
        if not os.path.exists(transcript_path):
            time.sleep(2)
            continue
            
        new_lines = []
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        step = json.loads(line)
                        idx = step.get("step_index", 0)
                        if idx > last_idx:
                            new_lines.append(step)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Lỗi đọc file transcript trong continuous loop: {e}")
            time.sleep(2)
            continue
            
        if new_lines:
            for step in new_lines:
                idx = step.get("step_index", 0)
                last_idx = max(last_idx, idx)
                
                step_type = step.get("type")
                source = step.get("source")
                content = step.get("content", "").strip()
                
                # Tránh vọng lại tin nhắn chính user vừa gửi từ Telegram
                if step_type == "USER_INPUT":
                    sent_msgs = last_sent_from_telegram.get(chat_id, [])
                    if content in sent_msgs:
                        sent_msgs.remove(content)
                        last_sent_from_telegram[chat_id] = sent_msgs
                        continue
                    send_message(chat_id, f"👤 *User (IDE):*\n{content}")
                    
                elif step_type == "PLANNER_RESPONSE" and source == "MODEL":
                    tool_calls = step.get("tool_calls", [])
                    if content:
                        send_message(chat_id, f"🤖 *IDE Agent:*\n\n{content}")
                    if tool_calls:
                        for tc in tool_calls:
                            name = tc.get("name", "tool")
                            args = tc.get("args", {})
                            summary = args.get("toolSummary", "") or args.get("toolAction", "") or name
                            summary = summary.strip('"\'')
                            send_message(chat_id, f"🛠️ *Agent đang thực thi:* `{summary}`")
                            
                elif step_type == "ASK_QUESTION":
                    send_message(chat_id, f"❓ *IDE Agent cần anh xác nhận (vui lòng vào IDE hoặc chat trực tiếp tại đây để trả lời):*\n\n{content}")
                    
                elif step_type == "ERROR_MESSAGE":
                    send_message(chat_id, f"❌ *IDE Agent gặp lỗi:* `{content}`")
                    
        time.sleep(1.5)

def handle_sync_command(chat_id: int, text: str):
    """Xử lý lệnh /sync."""
    args = text[5:].strip().lower()
    
    if args == "off":
        if is_sync_enabled(chat_id):
            stop_continuous_polling(chat_id)
            save_sync_config({"sync_enabled": False, "chat_id": None})
            send_message(chat_id, "📴 *Đã tắt đồng bộ hóa với IDE Agent.*\nBot quay lại chế độ chat luật trực tiếp.")
        else:
            send_message(chat_id, "ℹ️ Đồng bộ hóa vốn đang ở trạng thái tắt.")
    else:
        current_conv_id = get_current_conversation_id()
        if not current_conv_id:
            send_message(chat_id, "❌ Không tìm thấy `.conversation_id`. Cần bắt đầu chat trong IDE trước.")
            return
            
        save_sync_config({
            "sync_enabled": True,
            "chat_id": chat_id,
            "conversation_id": current_conv_id
        })
        start_continuous_polling(chat_id)
        send_message(
            chat_id, 
            f"🔗 *Đã bật đồng bộ hóa 2 chiều với IDE Agent!*\n"
            f"Conversation ID: `{current_conv_id}`\n\n"
            f"👉 Mọi tin nhắn gửi cho bot bây giờ sẽ được tự động chuyển trực tiếp vào ô chat IDE mà không cần gõ tiền tố `/agent`.\n"
            f"👉 Để tắt đồng bộ, hãy gõ `/sync off`."
        )

def send_message_to_agent(chat_id: int, command_text: str) -> bool:
    """Gửi âm thầm tin nhắn tới IDE Agent."""
    conversation_id = get_current_conversation_id()
    if not conversation_id:
        send_message(chat_id, "❌ Không tìm thấy `.conversation_id` hiện tại.")
        return False
        
    agentapi_path = "/Users/tonguyen/.gemini/antigravity-ide/bin/agentapi"
    try:
        result = subprocess.run(
            [agentapi_path, "send-message", conversation_id, command_text],
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode != 0:
            send_message(chat_id, f"❌ Lỗi gửi lệnh đến Agent: {result.stderr or result.stdout}")
            return False
        return True
    except Exception as e:
        send_message(chat_id, f"❌ Lỗi thực thi agentapi: {str(e)}")
        return False


# ══════════════════════════════════════════════════
# IDE AGENT INTEGRATION (agentapi & transcript polling)
# ══════════════════════════════════════════════════

active_polls = {}

def get_current_conversation_id() -> Optional[str]:
    """Đọc conversation_id hiện tại từ file cấu hình."""
    try:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".conversation_id"
        )
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Lỗi đọc .conversation_id: {e}")
    return None


def get_latest_step_index(conversation_id: str) -> int:
    """Lấy step_index lớn nhất hiện tại từ transcript.jsonl."""
    transcript_path = f"/Users/tonguyen/.gemini/antigravity-ide/brain/{conversation_id}/.system_generated/logs/transcript.jsonl"
    if not os.path.exists(transcript_path):
        return 0
    max_idx = 0
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    step = json.loads(line)
                    idx = step.get("step_index", 0)
                    if idx > max_idx:
                        max_idx = idx
                except:
                    pass
    except Exception as e:
        logger.error(f"Lỗi đọc step_index: {e}")
    return max_idx


def poll_agent_response(chat_id: int, conversation_id: str, start_step_index: int):
    """Poll transcript.jsonl để nhận phản hồi từ IDE Agent."""
    transcript_path = f"/Users/tonguyen/.gemini/antigravity-ide/brain/{conversation_id}/.system_generated/logs/transcript.jsonl"
    
    logger.info(f"Bắt đầu poll transcript cho conv {conversation_id} từ step_index {start_step_index}")
    
    last_idx = start_step_index
    no_update_count = 0
    max_no_update = 240  # Dừng sau 6 phút không có hoạt động
    
    active_polls[chat_id] = True
    
    try:
        while active_polls.get(chat_id):
            if not os.path.exists(transcript_path):
                time.sleep(2)
                continue
                
            new_lines = []
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            step = json.loads(line)
                            idx = step.get("step_index", 0)
                            if idx > last_idx:
                                new_lines.append(step)
                        except Exception as e:
                            pass
            except Exception as e:
                logger.error(f"Lỗi đọc file transcript: {e}")
                time.sleep(2)
                continue
                
            if new_lines:
                no_update_count = 0
                for step in new_lines:
                    idx = step.get("step_index", 0)
                    last_idx = max(last_idx, idx)
                    
                    step_type = step.get("type")
                    source = step.get("source")
                    
                    if step_type == "PLANNER_RESPONSE" and source == "MODEL":
                        content = step.get("content", "").strip()
                        tool_calls = step.get("tool_calls", [])
                        
                        if content:
                            send_message(chat_id, f"🤖 *IDE Agent:*\n\n{content}")
                            
                        if tool_calls:
                            for tc in tool_calls:
                                name = tc.get("name", "tool")
                                args = tc.get("args", {})
                                summary = args.get("toolSummary", "") or args.get("toolAction", "") or name
                                # Bỏ các dấu ngoặc kép thừa từ toolSummary/toolAction nếu có
                                summary = summary.strip('"\'')
                                send_message(chat_id, f"🛠️ *Agent đang thực thi:* `{summary}`")
                        
                        if not tool_calls:
                            send_message(chat_id, "✅ *IDE Agent đã hoàn thành lượt xử lý.*")
                            active_polls[chat_id] = False
                            return
                            
                    elif step_type == "ASK_QUESTION":
                        content = step.get("content", "").strip()
                        send_message(chat_id, f"❓ *IDE Agent cần anh xác nhận (vui lòng vào IDE để trả lời):*\n\n{content}")
                        active_polls[chat_id] = False
                        return
                        
                    elif step_type == "ERROR_MESSAGE":
                        content = step.get("content", "").strip()
                        send_message(chat_id, f"❌ *IDE Agent gặp lỗi:* `{content}`")
                        active_polls[chat_id] = False
                        return
            else:
                no_update_count += 1
                if no_update_count > max_no_update:
                    send_message(chat_id, "⚠️ *Thời gian chờ IDE Agent phản hồi quá lâu (Timeout 6 phút).*")
                    active_polls[chat_id] = False
                    return
                    
            time.sleep(1.5)
            
    except Exception as e:
        logger.error(f"Lỗi trong luồng poll agent: {e}")
        send_message(chat_id, f"⚠️ Gặp sự cố khi theo dõi phản hồi của Agent: {str(e)}")
    finally:
        active_polls[chat_id] = False


def handle_agent_command(chat_id: int, command_text: str):
    """Gửi lệnh đến IDE Agent qua agentapi và theo dõi phản hồi."""
    if not command_text:
        send_message(chat_id, "💻 Cú pháp: `/agent [lệnh]`\nVí dụ: `/agent viết test case cho chatbot.py`")
        return
        
    if active_polls.get(chat_id):
        send_message(chat_id, "⏳ Agent vẫn đang thực thi lệnh trước. Vui lòng đợi đến khi hoàn thành.")
        return
        
    conversation_id = get_current_conversation_id()
    if not conversation_id:
        send_message(chat_id, "❌ Không tìm thấy file `.conversation_id` hiện tại. Agent cần cập nhật file này trước.")
        return
        
    start_step_index = get_latest_step_index(conversation_id)
    
    send_message(chat_id, f"📥 *Đang gửi lệnh đến IDE Agent...*\n💬 *Lệnh:* _{command_text}_")
    
    agentapi_path = "/Users/tonguyen/.gemini/antigravity-ide/bin/agentapi"
    try:
        import subprocess
        # Chạy command gửi message
        result = subprocess.run(
            [agentapi_path, "send-message", conversation_id, command_text],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode != 0:
            send_message(chat_id, f"❌ Lỗi gửi lệnh đến Agent: {result.stderr or result.stdout}")
            return
            
        import threading
        t = threading.Thread(
            target=poll_agent_response,
            args=(chat_id, conversation_id, start_step_index),
            daemon=True
        )
        t.start()
        
    except Exception as e:
        send_message(chat_id, f"❌ Lỗi thực thi agentapi: {str(e)}")


# ══════════════════════════════════════════════════
# MAIN POLLING LOOP
# ══════════════════════════════════════════════════

def process_update(update: dict):
    """Xử lý một update từ Telegram."""
    msg = update.get("message")
    if not msg:
        return
    
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    user_name = msg["from"].get("first_name", "User")
    text = msg.get("text", "").strip()
    message_id = msg["message_id"]
    
    if not text:
        return
    
    # Access control
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        send_message(chat_id, "🔒 Bạn không có quyền sử dụng bot này.")
        return
    
    # Rate limiting
    if not check_rate_limit(user_id):
        send_message(chat_id, "⏳ Bạn gửi quá nhanh. Vui lòng đợi 1 phút.")
        return
    
    logger.info(f"[{user_id}] @{msg['from'].get('username', 'N/A')}: {text[:100]}")
    
    # Command routing
    if text.startswith("/start"):
        handle_start(chat_id, user_name)
    elif text.startswith("/help"):
        handle_help(chat_id)
    elif text.startswith("/status"):
        handle_status(chat_id)
    elif text.startswith("/benchmark"):
        handle_benchmark(chat_id)
    elif text.startswith("/search"):
        query = text[7:].strip()
        handle_search(chat_id, query)
    elif text.startswith("/agent"):
        command_text = text[6:].strip()
        handle_agent_command(chat_id, command_text)
    elif text.startswith("/sync"):
        handle_sync_command(chat_id, text)
    else:
        # Nếu đang đồng bộ, chuyển tiếp tin nhắn thường sang IDE
        if is_sync_enabled(chat_id):
            if chat_id not in last_sent_from_telegram:
                last_sent_from_telegram[chat_id] = []
            last_sent_from_telegram[chat_id].append(text)
            
            # Gửi tin nhắn đến IDE Agent
            send_message_to_agent(chat_id, text)
        else:
            # Chat pháp luật trực tiếp
            handle_chat(chat_id, user_id, text, message_id)


def main():
    """Main polling loop — Long Polling."""
    print("=" * 60)
    print("⚖️  LuatBot Telegram — Trợ lý Pháp lý AI")
    print("=" * 60)
    
    # Kiểm tra kết nối Telegram
    me = tg_request("getMe")
    if me.get("ok"):
        bot_info = me["result"]
        print(f"✅ Bot: @{bot_info['username']} ({bot_info['first_name']})")
    else:
        print(f"❌ Không thể kết nối Telegram: {me}")
        sys.exit(1)
    
    # Kiểm tra LuatBot server
    health = check_server_health()
    if health["online"]:
        print(f"✅ LuatBot API: {LUATBOT_API_URL} — ONLINE")
    else:
        print(f"⚠️  LuatBot API: {LUATBOT_API_URL} — OFFLINE")
        print("   Bot sẽ vẫn chạy, nhưng không thể trả lời câu hỏi pháp luật.")
        print("   Khởi chạy server: python3 server.py")
    
    print(f"🔑 API Key: {LUATBOT_API_KEY[:15]}...")
    print()
    print("📱 Mở Telegram và chat với @" + me["result"]["username"])
    print("   Nhấn Ctrl+C để dừng bot.")
    print("=" * 60)
    
    # Set bot commands
    tg_request("setMyCommands", {
        "commands": [
            {"command": "start", "description": "🏠 Bắt đầu — Giới thiệu LuatBot"},
            {"command": "help", "description": "📖 Hướng dẫn sử dụng"},
            {"command": "search", "description": "🔍 Tìm kiếm văn bản pháp luật"},
            {"command": "status", "description": "📊 Kiểm tra trạng thái server"},
            {"command": "benchmark", "description": "📈 Xem kết quả benchmark LLM"},
            {"command": "agent", "description": "💻 Ra lệnh cho AI Agent trong IDE"},
            {"command": "sync", "description": "🔗 Đồng bộ 2 chiều trực tiếp với IDE Agent"},
        ]
    })
    
    # Khôi phục đồng bộ nếu trước đó đang bật
    sync_config = load_sync_config()
    if sync_config.get("sync_enabled") and sync_config.get("chat_id"):
        chat_id = sync_config["chat_id"]
        print(f"🔄 Khôi phục đồng bộ liên tục với chat_id: {chat_id}")
        start_continuous_polling(chat_id)
        
    # Long polling loop
    offset = 0
    error_count = 0
    
    while True:
        try:
            result = tg_request("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message"],
            }, timeout=35)
            
            if result.get("ok"):
                error_count = 0
                for update in result.get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        process_update(update)
                    except Exception as e:
                        logger.error(f"Error processing update: {e}", exc_info=True)
            else:
                error_count += 1
                logger.warning(f"getUpdates failed (attempt {error_count})")
                time.sleep(min(error_count * 2, 30))
                
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user.")
            break
        except Exception as e:
            error_count += 1
            logger.error(f"Polling error: {e}", exc_info=True)
            time.sleep(min(error_count * 2, 30))


if __name__ == "__main__":
    # Tạo thư mục logs nếu chưa có
    os.makedirs("logs", exist_ok=True)
    main()
