"""
progress_server.py — Dashboard server để theo dõi tiến độ crawl và kiểm tra data.
Chạy trên port 8899: python progress_server.py
"""
import os
import json
import sqlite3
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"
LOG_NAME = "fill_missing.log"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/dashboard":
            self.serve_dashboard()
        elif path == "/api/stats":
            self.serve_stats()
        elif path == "/api/logs":
            self.serve_logs()
        elif path == "/api/sample":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [5])[0])
            self.serve_sample(limit)
        elif path == "/api/check":
            qs = parse_qs(parsed.query)
            doc_id = qs.get("id", [None])[0]
            self.serve_check(doc_id)
        else:
            super().do_GET()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def serve_stats(self):
        try:
            conn = sqlite3.connect(DB_NAME, timeout=5)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM documents")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM documents WHERE has_content = 1")
            with_content = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM documents WHERE has_content = 0")
            without_content = c.fetchone()[0]

            # Thống kê theo loại văn bản
            c.execute("SELECT loai_van_ban, COUNT(*) FROM documents GROUP BY loai_van_ban ORDER BY COUNT(*) DESC LIMIT 10")
            by_type = [{"name": r[0] or "Không xác định", "count": r[1]} for r in c.fetchall()]

            # Thống kê relationships
            c.execute("SELECT COUNT(*) FROM relationships")
            total_rels = c.fetchone()[0]

            # Thống kê article_modifications
            try:
                c.execute("SELECT COUNT(*) FROM article_modifications")
                total_mods = c.fetchone()[0]
            except:
                total_mods = 0

            # Thống kê FTS
            try:
                c.execute("SELECT COUNT(*) FROM documents_fts")
                fts_count = c.fetchone()[0]
            except:
                fts_count = 0

            # Content store size
            content_size = 0
            if os.path.exists(CONTENT_DB):
                content_size = os.path.getsize(CONTENT_DB)

            conn.close()

            self.send_json({
                "total_documents": total,
                "with_content": with_content,
                "without_content": without_content,
                "progress_pct": round(with_content / total * 100, 2) if total > 0 else 0,
                "by_type": by_type,
                "total_relationships": total_rels,
                "total_modifications": total_mods,
                "fts_indexed": fts_count,
                "content_db_size_mb": round(content_size / 1024 / 1024, 1),
                "main_db_size_mb": round(os.path.getsize(DB_NAME) / 1024 / 1024, 1),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def serve_logs(self):
        try:
            if os.path.exists(LOG_NAME):
                with open(LOG_NAME, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                # Return last 100 lines
                self.send_json({"lines": lines[-100:], "total_lines": len(lines)})
            else:
                self.send_json({"lines": [], "total_lines": 0})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def serve_sample(self, limit=5):
        try:
            conn = sqlite3.connect(DB_NAME, timeout=5)
            conn_content = sqlite3.connect(CONTENT_DB, timeout=5)
            c = conn.cursor()
            cc = conn_content.cursor()

            # Lấy sample những văn bản vừa tải xong (has_content=1, ID lớn nhất)
            c.execute("""
                SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh, tinh_trang_hieu_luc
                FROM documents WHERE has_content = 1
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            docs = []
            for row in c.fetchall():
                doc = {
                    "id": row[0], "title": row[1], "so_ky_hieu": row[2],
                    "loai_van_ban": row[3], "ngay_ban_hanh": row[4],
                    "tinh_trang": row[5],
                }
                # Check content length
                cc.execute("SELECT LENGTH(content_html) FROM document_content WHERE doc_id = ?", (row[0],))
                cr = cc.fetchone()
                doc["content_length"] = cr[0] if cr else 0
                docs.append(doc)

            conn.close()
            conn_content.close()
            self.send_json({"documents": docs})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def serve_check(self, doc_id):
        if not doc_id:
            self.send_json({"error": "Missing id parameter"}, 400)
            return
        try:
            conn = sqlite3.connect(DB_NAME, timeout=5)
            conn_content = sqlite3.connect(CONTENT_DB, timeout=5)
            c = conn.cursor()
            cc = conn_content.cursor()

            c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            row = c.fetchone()
            if not row:
                self.send_json({"error": f"Document {doc_id} not found"}, 404)
                return

            cols = [desc[0] for desc in c.description]
            doc = dict(zip(cols, row))

            # Get content preview
            cc.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (doc_id,))
            cr = cc.fetchone()
            if cr and cr[0]:
                doc["content_preview"] = cr[0][:2000]
                doc["content_length"] = len(cr[0])
            else:
                doc["content_preview"] = None
                doc["content_length"] = 0

            # Get relationships
            c.execute("""
                SELECT r.other_doc_id, r.relationship, d.title
                FROM relationships r
                LEFT JOIN documents d ON d.id = r.other_doc_id
                WHERE r.doc_id = ?
                LIMIT 20
            """, (doc_id,))
            doc["relationships"] = [
                {"other_id": r[0], "type": r[1], "other_title": r[2]}
                for r in c.fetchall()
            ]

            # Get article_modifications
            try:
                c.execute("""
                    SELECT am.article_name, am.modified_by_doc_id, am.modified_text, d.title
                    FROM article_modifications am
                    LEFT JOIN documents d ON d.id = am.modified_by_doc_id
                    WHERE am.doc_id = ?
                """, (doc_id,))
                doc["modifications"] = [
                    {"article": r[0], "by_doc_id": r[1], "text": r[2][:200], "by_title": r[3]}
                    for r in c.fetchall()
                ]
            except:
                doc["modifications"] = []

            conn.close()
            conn_content.close()
            self.send_json(doc)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def serve_dashboard(self):
        html = DASHBOARD_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress default logging


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 Data Crawler Dashboard — dataluatvn</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg-primary: #0a0e1a;
  --bg-card: #111827;
  --bg-card-hover: #1a2236;
  --bg-input: #1e293b;
  --border: #1e293b;
  --border-accent: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent-blue: #3b82f6;
  --accent-cyan: #06b6d4;
  --accent-green: #10b981;
  --accent-amber: #f59e0b;
  --accent-red: #ef4444;
  --accent-purple: #8b5cf6;
  --gradient-1: linear-gradient(135deg, #3b82f6, #06b6d4);
  --gradient-2: linear-gradient(135deg, #10b981, #06b6d4);
  --gradient-3: linear-gradient(135deg, #f59e0b, #ef4444);
  --gradient-4: linear-gradient(135deg, #8b5cf6, #ec4899);
  --shadow: 0 4px 24px rgba(0,0,0,0.3);
  --radius: 16px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
}

/* Header */
.header {
  background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(6,182,212,0.1));
  border-bottom: 1px solid var(--border);
  padding: 20px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  backdrop-filter: blur(20px);
  position: sticky; top: 0; z-index: 100;
}
.header h1 {
  font-size: 22px; font-weight: 700;
  background: var(--gradient-1);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.header .status {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--text-secondary);
}
.header .status .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent-green);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.container { max-width: 1400px; margin: 0 auto; padding: 24px; }

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: transform 0.2s, border-color 0.2s;
}
.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-accent);
}
.stat-card .label {
  font-size: 12px; font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}
.stat-card .value {
  font-size: 28px; font-weight: 800;
  line-height: 1;
}
.stat-card .sub {
  font-size: 12px; color: var(--text-secondary);
  margin-top: 6px;
}
.stat-card .icon {
  position: absolute; right: 16px; top: 50%;
  transform: translateY(-50%);
  font-size: 40px; opacity: 0.15;
}
.stat-card.blue .value { color: var(--accent-blue); }
.stat-card.green .value { color: var(--accent-green); }
.stat-card.amber .value { color: var(--accent-amber); }
.stat-card.purple .value { color: var(--accent-purple); }
.stat-card.cyan .value { color: var(--accent-cyan); }
.stat-card.red .value { color: var(--accent-red); }

/* Progress Bar */
.progress-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 24px;
}
.progress-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.progress-header h2 { font-size: 16px; font-weight: 600; }
.progress-header .pct {
  font-size: 24px; font-weight: 800;
  background: var(--gradient-2);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.progress-bar-bg {
  width: 100%; height: 12px;
  background: var(--bg-input);
  border-radius: 6px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--gradient-2);
  border-radius: 6px;
  transition: width 1s ease;
  position: relative;
}
.progress-bar-fill::after {
  content: '';
  position: absolute; right: 0; top: 0;
  width: 30px; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3));
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  0% { opacity: 0; }
  50% { opacity: 1; }
  100% { opacity: 0; }
}
.progress-details {
  display: flex; gap: 24px; margin-top: 12px;
  font-size: 13px; color: var(--text-secondary);
}
.progress-details span { display: flex; align-items: center; gap: 6px; }
.progress-details .dot-green { color: var(--accent-green); }
.progress-details .dot-red { color: var(--accent-red); }

/* Two Column Layout */
.two-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}
@media (max-width: 900px) {
  .two-cols { grid-template-columns: 1fr; }
}

/* Log Panel */
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
}
.panel-header h3 { font-size: 14px; font-weight: 600; }
.panel-body { padding: 16px 20px; max-height: 400px; overflow-y: auto; }
.panel-body::-webkit-scrollbar { width: 6px; }
.panel-body::-webkit-scrollbar-thumb { background: var(--border-accent); border-radius: 3px; }

.log-line {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: nowrap;
}
.log-line .time { color: var(--text-muted); }
.log-line .success { color: var(--accent-green); }
.log-line .error { color: var(--accent-red); }
.log-line .info { color: var(--accent-cyan); }

/* Doc Check */
.check-input {
  display: flex; gap: 8px; margin-bottom: 16px;
}
.check-input input {
  flex: 1;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 16px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}
.check-input input:focus { border-color: var(--accent-blue); }
.check-input button {
  background: var(--gradient-1);
  border: none; border-radius: 10px;
  padding: 10px 20px;
  color: white; font-weight: 600; font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}
.check-input button:hover { opacity: 0.85; }

.doc-result {
  font-size: 13px; color: var(--text-secondary);
  line-height: 1.8;
}
.doc-result .field { color: var(--text-muted); }
.doc-result .val { color: var(--text-primary); font-weight: 500; }
.doc-result .tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.doc-result .tag.ok { background: rgba(16,185,129,0.15); color: var(--accent-green); }
.doc-result .tag.no { background: rgba(239,68,68,0.15); color: var(--accent-red); }
.doc-result .rel-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

/* Sample table */
.sample-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.sample-table th {
  text-align: left; padding: 10px 12px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
}
.sample-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}
.sample-table tr:hover td { background: var(--bg-card-hover); }
.sample-table .title-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  font-weight: 500;
}

/* Auto-refresh badge */
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px; font-weight: 600;
  background: rgba(59,130,246,0.1);
  color: var(--accent-blue);
}
</style>
</head>
<body>

<div class="header">
  <h1>📊 Data Crawler Dashboard</h1>
  <div class="status">
    <div class="dot"></div>
    <span id="lastUpdate">Đang tải...</span>
    <span class="badge">🔄 Auto-refresh 5s</span>
  </div>
</div>

<div class="container">
  <!-- Stats -->
  <div class="stats-grid" id="statsGrid"></div>

  <!-- Progress -->
  <div class="progress-section" id="progressSection"></div>

  <!-- Two Columns: Logs + Check -->
  <div class="two-cols">
    <div class="panel">
      <div class="panel-header">
        <h3>📜 Crawl Logs (realtime)</h3>
        <span class="badge" id="logCount">0 lines</span>
      </div>
      <div class="panel-body" id="logBody"></div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h3>🔍 Kiểm tra Văn bản</h3>
      </div>
      <div class="panel-body">
        <div class="check-input">
          <input type="text" id="checkId" placeholder="Nhập Document ID (vd: 96122)" onkeypress="if(event.key==='Enter')checkDoc()">
          <button onclick="checkDoc()">Kiểm tra</button>
        </div>
        <div id="checkResult" class="doc-result"></div>
      </div>
    </div>
  </div>

  <!-- Recent Documents -->
  <div class="panel" style="margin-top: 16px;">
    <div class="panel-header">
      <h3>📄 Văn bản vừa tải gần đây</h3>
    </div>
    <div class="panel-body" style="max-height:500px;padding:0;">
      <table class="sample-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Tiêu đề</th>
            <th>Số ký hiệu</th>
            <th>Loại</th>
            <th>Ngày BH</th>
            <th>Content</th>
          </tr>
        </thead>
        <tbody id="sampleBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const API = '';

function formatNum(n) {
  return n?.toLocaleString('vi-VN') ?? '0';
}

function colorLog(line) {
  return line
    .replace(/✅/g, '<span class="success">✅</span>')
    .replace(/❌/g, '<span class="error">❌</span>')
    .replace(/⚠️/g, '<span class="error">⚠️</span>')
    .replace(/🚀|🎉|📊|⏳|🔗|📋|⚡/g, '<span class="info">$&</span>')
    .replace(/\[([^\]]+)\]/, '<span class="time">[$1]</span>');
}

async function fetchStats() {
  try {
    const res = await fetch(API + '/api/stats');
    const d = await res.json();
    
    document.getElementById('lastUpdate').textContent = d.timestamp;

    document.getElementById('statsGrid').innerHTML = `
      <div class="stat-card blue">
        <div class="label">Tổng Văn bản</div>
        <div class="value">${formatNum(d.total_documents)}</div>
        <div class="sub">Main DB: ${d.main_db_size_mb} MB</div>
        <div class="icon">📚</div>
      </div>
      <div class="stat-card green">
        <div class="label">Có nội dung</div>
        <div class="value">${formatNum(d.with_content)}</div>
        <div class="sub">Content DB: ${d.content_db_size_mb} MB</div>
        <div class="icon">✅</div>
      </div>
      <div class="stat-card red">
        <div class="label">Thiếu nội dung</div>
        <div class="value">${formatNum(d.without_content)}</div>
        <div class="sub">Đang tải...</div>
        <div class="icon">⏳</div>
      </div>
      <div class="stat-card cyan">
        <div class="label">FTS Indexed</div>
        <div class="value">${formatNum(d.fts_indexed)}</div>
        <div class="sub">Full-text search</div>
        <div class="icon">🔍</div>
      </div>
      <div class="stat-card purple">
        <div class="label">Liên kết</div>
        <div class="value">${formatNum(d.total_relationships)}</div>
        <div class="sub">Relationships</div>
        <div class="icon">🔗</div>
      </div>
      <div class="stat-card amber">
        <div class="label">Sửa đổi</div>
        <div class="value">${formatNum(d.total_modifications)}</div>
        <div class="sub">Article Modifications</div>
        <div class="icon">📝</div>
      </div>
    `;

    document.getElementById('progressSection').innerHTML = `
      <div class="progress-header">
        <h2>Tiến độ tải nội dung</h2>
        <div class="pct">${d.progress_pct}%</div>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:${d.progress_pct}%"></div>
      </div>
      <div class="progress-details">
        <span><span class="dot-green">●</span> Đã tải: ${formatNum(d.with_content)}</span>
        <span><span class="dot-red">●</span> Còn lại: ${formatNum(d.without_content)}</span>
        <span>📊 Tổng: ${formatNum(d.total_documents)}</span>
      </div>
    `;
  } catch(e) {
    console.error('Stats error:', e);
  }
}

async function fetchLogs() {
  try {
    const res = await fetch(API + '/api/logs');
    const d = await res.json();
    const el = document.getElementById('logBody');
    const wasAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    
    el.innerHTML = d.lines.map(l => `<div class="log-line">${colorLog(l.trim())}</div>`).join('');
    document.getElementById('logCount').textContent = `${d.total_lines} lines`;
    
    if (wasAtBottom) el.scrollTop = el.scrollHeight;
  } catch(e) {}
}

async function fetchSample() {
  try {
    const res = await fetch(API + '/api/sample?limit=15');
    const d = await res.json();
    document.getElementById('sampleBody').innerHTML = d.documents.map(doc => `
      <tr>
        <td><a href="javascript:void(0)" onclick="document.getElementById('checkId').value='${doc.id}';checkDoc();" style="color:var(--accent-blue)">${doc.id}</a></td>
        <td class="title-cell" title="${doc.title}">${doc.title || '-'}</td>
        <td>${doc.so_ky_hieu || '-'}</td>
        <td>${(doc.loai_van_ban || '-').substring(0, 20)}</td>
        <td>${doc.ngay_ban_hanh || '-'}</td>
        <td>${doc.content_length > 0 ? '<span class="tag ok">' + formatNum(doc.content_length) + ' bytes</span>' : '<span class="tag no">Empty</span>'}</td>
      </tr>
    `).join('');
  } catch(e) {}
}

async function checkDoc() {
  const id = document.getElementById('checkId').value.trim();
  if (!id) return;
  const el = document.getElementById('checkResult');
  el.innerHTML = '<span style="color:var(--accent-cyan)">Đang kiểm tra...</span>';
  
  try {
    const res = await fetch(API + '/api/check?id=' + id);
    const d = await res.json();
    if (d.error) {
      el.innerHTML = `<span style="color:var(--accent-red)">❌ ${d.error}</span>`;
      return;
    }
    
    let html = `
      <div style="margin-bottom:12px">
        <div><span class="field">ID:</span> <span class="val">${d.id}</span></div>
        <div><span class="field">Tiêu đề:</span> <span class="val">${d.title || '-'}</span></div>
        <div><span class="field">Số KH:</span> <span class="val">${d.so_ky_hieu || '-'}</span></div>
        <div><span class="field">Loại:</span> <span class="val">${d.loai_van_ban || '-'}</span></div>
        <div><span class="field">Ngày BH:</span> <span class="val">${d.ngay_ban_hanh || '-'}</span></div>
        <div><span class="field">Hiệu lực:</span> <span class="val">${d.tinh_trang_hieu_luc || '-'}</span></div>
        <div><span class="field">Content:</span> ${d.content_length > 0 ? '<span class="tag ok">✅ ' + formatNum(d.content_length) + ' bytes</span>' : '<span class="tag no">❌ Chưa có</span>'}</div>
      </div>
    `;

    if (d.content_preview) {
      html += `<div style="margin-bottom:12px">
        <div class="field" style="margin-bottom:4px">📝 Preview nội dung:</div>
        <div style="background:var(--bg-input);padding:8px 12px;border-radius:8px;font-size:11px;max-height:150px;overflow-y:auto;color:var(--text-secondary)">${d.content_preview.substring(0,500)}...</div>
      </div>`;
    }

    if (d.relationships?.length > 0) {
      html += `<div><div class="field" style="margin-bottom:4px">🔗 Liên kết (${d.relationships.length}):</div>`;
      d.relationships.slice(0, 8).forEach(r => {
        html += `<div class="rel-item"><span style="color:var(--accent-cyan)">${r.type}</span> → <a href="javascript:void(0)" onclick="document.getElementById('checkId').value='${r.other_id}';checkDoc();" style="color:var(--accent-blue)">#${r.other_id}</a> ${(r.other_title || '').substring(0, 60)}</div>`;
      });
      html += '</div>';
    }

    if (d.modifications?.length > 0) {
      html += `<div style="margin-top:8px"><div class="field" style="margin-bottom:4px">📝 Sửa đổi (${d.modifications.length}):</div>`;
      d.modifications.slice(0, 5).forEach(m => {
        html += `<div class="rel-item"><span style="color:var(--accent-amber)">${m.article}</span> bởi <a href="javascript:void(0)" onclick="document.getElementById('checkId').value='${m.by_doc_id}';checkDoc();" style="color:var(--accent-blue)">#${m.by_doc_id}</a></div>`;
      });
      html += '</div>';
    }

    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = `<span style="color:var(--accent-red)">❌ Lỗi: ${e.message}</span>`;
  }
}

// Initial load + auto-refresh
fetchStats(); fetchLogs(); fetchSample();
setInterval(fetchStats, 5000);
setInterval(fetchLogs, 3000);
setInterval(fetchSample, 10000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = 8899
    print(f"🚀 Dashboard server running at http://localhost:{port}")
    print(f"   Database: {os.path.abspath(DB_NAME)}")
    print(f"   Content DB: {os.path.abspath(CONTENT_DB)}")
    print(f"   Log file: {os.path.abspath(LOG_NAME)}")
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped.")
