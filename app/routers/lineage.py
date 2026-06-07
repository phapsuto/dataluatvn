import re
import sqlite3
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Path, Query, HTTPException

from app.dependencies import require_api_key
from app.database import get_db_connection
from app.utils.legal_logic import get_document_rank, compare_hierarchy

router = APIRouter(prefix="/laws", tags=["🔗 Cây phả hệ & Chồng chéo luật"])


# ╔══════════════════════════════════════════════════════════════╗
# ║                      SCHEMAS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class GraphNode(BaseModel):
    id: int
    label: str
    title: str  # HTML Tooltip
    group: str
    color: Dict[str, str]
    value: int
    font: Dict[str, Any]

class GraphEdge(BaseModel):
    from_node: int = Query(..., alias="from")
    to_node: int = Query(..., alias="to")
    label: str
    color: Dict[str, str]
    arrows: str

    class Config:
        populate_by_name = True

class LineageResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]

class OverlapDetail(BaseModel):
    doc_id: int
    title: str
    so_ky_hieu: Optional[str]
    loai_van_ban: Optional[str]
    co_quan_ban_hanh: Optional[str]
    ngay_ban_hanh: Optional[str]
    tinh_trang_hieu_luc: Optional[str]
    linh_vuc: Optional[str]
    relationship: str
    preferred: bool
    reason: str
    clause: str


# ╔══════════════════════════════════════════════════════════════╗
# ║                      HELPERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def get_node_styling(doc: Dict[str, Any], is_target: bool = False) -> Dict[str, Any]:
    """Tạo kiểu dáng trực quan cho Node dựa trên loại văn bản."""
    loai = (doc.get("loai_van_ban") or "").strip().lower()
    co_quan = (doc.get("co_quan_ban_hanh") or "").strip().lower()
    ky_hieu = (doc.get("so_ky_hieu") or "").strip().upper()

    # Nhóm mặc định
    group = "Khác"
    bg_color = "#475569" # Slate
    border_color = "#334155"

    if is_target:
        group = "Văn bản đang xem"
        bg_color = "#f59e0b" # Amber/Gold
        border_color = "#d97706"
    elif "hiến pháp" in loai:
        group = "Hiến pháp"
        bg_color = "#dc2626" # Red
        border_color = "#991b1b"
    elif loai in ["bộ luật", "luật"]:
        group = "Luật / Bộ luật"
        bg_color = "#dc2626" # Red
        border_color = "#991b1b"
    elif loai == "pháp lệnh":
        group = "Pháp lệnh"
        bg_color = "#ea580c" # Orange
        border_color = "#9a3412"
    elif loai == "nghị định":
        group = "Nghị định"
        bg_color = "#1d4ed8" # Blue
        border_color = "#1e3a8a"
    elif loai == "quyết định":
        group = "Quyết định"
        bg_color = "#9333ea" # Purple
        border_color = "#6b21a8"
    elif "thông tư" in loai or "thông tư liên tịch" in loai:
        group = "Thông tư"
        bg_color = "#0891b2" # Cyan
        border_color = "#0e7490"
    elif "hđnd" in ky_hieu or "ubnd" in ky_hieu or "hội đồng nhân dân" in co_quan or "ủy ban nhân dân" in co_quan:
        # Kiểm tra 2 cấp địa phương
        if any(w in co_quan for w in ["xã", "phường", "thị trấn"]):
            group = "Địa phương - Cấp Xã"
            bg_color = "#0d9488" # Teal
            border_color = "#115e59"
        else:
            group = "Địa phương - Cấp Tỉnh"
            bg_color = "#16a34a" # Green
            border_color = "#14532d"

    # HTML Tooltip cực đẹp (Glassmorphism inspired styling in title)
    title_tooltip = f"""
    <div style="background:#1e293b; color:#f1f5f9; padding:10px 14px; border-radius:8px; max-width:300px; font-size:12px; font-family:sans-serif; line-height:1.5; box-shadow:0 4px 12px rgba(0,0,0,0.3)">
      <strong style="color:#38bdf8; font-size:13px; display:block; margin-bottom:4px;">{doc.get('so_ky_hieu') or 'Không số ký hiệu'}</strong>
      <div style="margin-bottom:6px;">{doc.get('title')}</div>
      <span style="color:#94a3b8">Loại:</span> {doc.get('loai_van_ban') or 'N/A'}<br>
      <span style="color:#94a3b8">Ban hành:</span> {doc.get('co_quan_ban_hanh') or 'N/A'}<br>
      <span style="color:#94a3b8">Ngày ban hành:</span> {doc.get('ngay_ban_hanh') or 'N/A'}<br>
      <span style="color:#94a3b8">Tình trạng:</span> <span style="color:{'#4ade80' if doc.get('tinh_trang_hieu_luc') == 'Còn hiệu lực' else '#f87171'}">{doc.get('tinh_trang_hieu_luc') or 'N/A'}</span>
    </div>
    """

    return {
        "group": group,
        "color": {"background": bg_color, "border": border_color},
        "title": title_tooltip,
        "value": 30 if is_target else 20
    }


def get_edge_styling(relationship: str) -> Dict[str, Any]:
    """Tạo màu sắc và chiều mũi tên cho Edge."""
    rel = relationship.lower()
    edge_color = "#64748b" # Slate mặc định

    if "căn cứ" in rel:
        edge_color = "#10b981" # Green
    elif "sửa đổi" in rel or "bổ sung" in rel:
        edge_color = "#3b82f6" # Blue
    elif "hết hiệu lực" in rel or "đình chỉ" in rel:
        edge_color = "#ef4444" # Red
    elif "hướng dẫn" in rel or "hd, qđ" in rel:
        edge_color = "#8b5cf6" # Violet

    return {
        "color": {"color": edge_color, "highlight": "#f59e0b", "hover": "#f59e0b"},
        "arrows": "to"
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║                      ROUTERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

@router.get("/{law_id}/lineage", response_model=LineageResponse, summary="Cây phả hệ liên kết của văn bản")
def get_law_lineage(
    law_id: int = Path(..., description="ID văn bản cần vẽ đồ thị phả hệ"),
    _key=Depends(require_api_key),
):
    """
    Truy vấn đệ quy/nhiều bước để xây dựng mạng lưới quan hệ (lineage) của văn bản.
    Đầu ra chuẩn hóa danh sách `nodes` và `edges` để nạp trực tiếp vào thư viện `vis-network`.
    
    **Các mối quan hệ hướng dọc:** Căn cứ ban hành (Parents) -> Văn bản hướng dẫn thi hành (Children).
    **Các mối quan hệ hướng ngang:** Sửa đổi, bổ sung, thay thế, đình chỉ.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Lấy thông tin văn bản gốc
    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    target_row = cursor.fetchone()
    if not target_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản ID {law_id}")
    
    target_doc = dict(target_row)

    # 2. Truy vấn quan hệ trực tiếp (1-hop)
    cursor.execute("""
        SELECT doc_id, other_doc_id, relationship 
        FROM relationships 
        WHERE doc_id = ? OR other_doc_id = ?
    """, (law_id, law_id))
    direct_rels = [dict(row) for row in cursor.fetchall()]

    # Thu thập tất cả các ID liên quan trực tiếp
    connected_ids = {law_id}
    for r in direct_rels:
        connected_ids.add(r['doc_id'])
        connected_ids.add(r['other_doc_id'])

    # 3. Nếu số lượng node nhỏ (< 15), mở rộng thêm 1 hop của các node con để tạo đồ thị liên kết phong phú
    all_rels = list(direct_rels)
    if len(connected_ids) < 15:
        neighbors = list(connected_ids - {law_id})
        if neighbors:
            placeholders = ",".join(["?"] * len(neighbors))
            # Lấy thêm quan hệ của các neighbor (giới hạn 100 dòng để tránh bùng nổ đồ thị)
            cursor.execute(f"""
                SELECT doc_id, other_doc_id, relationship 
                FROM relationships 
                WHERE doc_id IN ({placeholders}) OR other_doc_id IN ({placeholders}) 
                LIMIT 100
            """, neighbors + neighbors)
            extra_rels = [dict(row) for row in cursor.fetchall()]
            
            # Gộp và lọc trùng
            existing_pairs = {f"{r['doc_id']}|{r['other_doc_id']}|{r['relationship']}" for r in all_rels}
            for er in extra_rels:
                pair_key = f"{er['doc_id']}|{er['other_doc_id']}|{er['relationship']}"
                if pair_key not in existing_pairs:
                    all_rels.append(er)
                    connected_ids.add(er['doc_id'])
                    connected_ids.add(er['other_doc_id'])

    # Giới hạn tối đa 60 nodes để đảm bảo hiệu năng vẽ đồ thị
    final_node_ids = list(connected_ids)[:60]
    
    # Fetch toàn bộ thông tin metadata của các node
    if not final_node_ids:
        conn.close()
        return {"nodes": [], "edges": []}

    placeholders = ",".join(["?"] * len(final_node_ids))
    cursor.execute(f"SELECT * FROM documents WHERE id IN ({placeholders})", final_node_ids)
    nodes_rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # 4. Biến đổi dữ liệu sang định dạng vis-network
    nodes = []
    for doc in nodes_rows:
        is_tgt = (doc["id"] == law_id)
        style = get_node_styling(doc, is_target=is_tgt)
        
        # Nhãn hiển thị ngắn gọn trên node
        label = doc.get("so_ky_hieu") or (doc.get("title")[:20] + "...")
        
        nodes.append({
            "id": doc["id"],
            "label": label,
            "title": style["title"],
            "group": style["group"],
            "color": style["color"],
            "value": style["value"],
            "font": {
                "size": 13,
                "color": "#ffffff",
                "face": "Segoe UI, Inter, sans-serif",
                "strokeWidth": 3,
                "strokeColor": "rgba(0,0,0,0.6)"
            }
        })

    edges = []
    for r in all_rels:
        # Chỉ giữ lại các quan hệ mà cả 2 node đều nằm trong danh sách cuối cùng
        if r['doc_id'] in final_node_ids and r['other_doc_id'] in final_node_ids:
            style = get_edge_styling(r['relationship'])
            
            # Chuẩn hóa hướng mũi tên từ cha đến con
            # Văn bản căn cứ: other_doc_id (cha) -> doc_id (con)
            # Văn bản được HD, QĐ chi tiết: other_doc_id (cha) -> doc_id (con)
            # Sửa đổi: other_doc_id (bản cũ) -> doc_id (bản sửa đổi)
            rel_name = r['relationship'].lower()
            from_node = r['doc_id']
            to_node = r['other_doc_id']

            if any(x in rel_name for x in ["văn bản căn cứ", "được hd, qđ chi tiết", "được sửa đổi", "được bổ sung"]):
                from_node = r['other_doc_id']
                to_node = r['doc_id']

            edges.append({
                "from": from_node,
                "to": to_node,
                "label": r['relationship'],
                "color": style["color"],
                "arrows": style["arrows"]
            })

    return {"nodes": nodes, "edges": edges}


@router.get("/{law_id}/overlaps", response_model=List[OverlapDetail], summary="Kiểm tra chồng chéo quy định của văn bản")
def check_law_overlaps(
    law_id: int = Path(..., description="ID văn bản cần kiểm tra chồng chéo"),
    _key=Depends(require_api_key),
):
    """
    Kiểm tra sự chồng chéo, mâu thuẫn quy định giữa văn bản hiện tại với các văn bản đang có hiệu lực.
    
    **Thuật toán:**
    1. Tìm các văn bản cùng lĩnh vực hoặc ngành đang trong trạng thái 'Còn hiệu lực' hoặc 'Hết hiệu lực một phần'.
    2. Quét chéo các từ khóa chính trích xuất từ tiêu đề văn bản bằng cơ chế FTS5 hoặc so khớp mối quan hệ.
    3. Áp dụng logic so sánh ưu tiên hiệu lực theo Điều 156 Luật 80/2015/QH13 (Cấp bậc cao hơn, hoặc Cùng cơ quan ban hành thì mới hơn).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Lấy thông tin văn bản gốc
    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    target_row = cursor.fetchone()
    if not target_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản ID {law_id}")
    
    target_doc = dict(target_row)
    linh_vuc = target_doc.get("linh_vuc")
    title = target_doc.get("title") or ""

    # Trích xuất từ khóa từ tiêu đề để tìm văn bản tương đương
    words = re.findall(r'\w+', title.lower())
    stopwords = {"về", "việc", "của", "và", "trong", "tại", "cho", "để", "ban", "hành", "nội", "dung", "một", "số", "quy", "định", "sửa", "đổi", "bổ", "sung", "áp", "dụng", "các", "như", "theo", "văn", "bản"}
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    # Lấy 3 từ khóa cốt lõi nhất
    keywords = keywords[:3]

    candidates = []

    # A. Tìm các văn bản liên kết trực tiếp trong bảng relationships (có khả năng chồng chéo cao nhất)
    cursor.execute("""
        SELECT d.*, r.relationship 
        FROM relationships r
        JOIN documents d ON (r.other_doc_id = d.id OR r.doc_id = d.id)
        WHERE (r.doc_id = ? OR r.other_doc_id = ?) 
          AND d.id != ?
          AND d.tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Hết hiệu lực một phần')
        LIMIT 10
    """, (law_id, law_id, law_id))
    for r in cursor.fetchall():
        d = dict(r)
        candidates.append(d)

    # B. Tìm các văn bản cùng lĩnh vực bằng FTS5 dựa trên từ khóa tiêu đề
    if keywords:
        fts_query = " OR ".join([f'"{kw}"' for kw in keywords])
        try:
            sql = """
                SELECT d.*, 'Cùng lĩnh vực' as relationship
                FROM documents d
                JOIN documents_fts f ON d.id = f.rowid
                WHERE d.id != ?
                  AND d.tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Hết hiệu lực một phần')
                  AND f.title MATCH ?
            """
            params = [law_id, fts_query]
            if linh_vuc:
                sql += " AND d.linh_vuc = ?"
                params.append(linh_vuc)
            sql += " LIMIT 8"
            
            cursor.execute(sql, params)
            for r in cursor.fetchall():
                d = dict(r)
                # Tránh trùng với danh sách quan hệ trực tiếp đã lấy
                if not any(c['id'] == d['id'] for c in candidates):
                    candidates.append(d)
        except sqlite3.OperationalError:
            # Phòng trường hợp FTS bị lỗi cú pháp
            pass

    # Nếu không tìm thấy bằng FTS, fallback lấy văn bản cùng ngành/lĩnh vực mới nhất
    if len(candidates) < 3 and linh_vuc:
        cursor.execute("""
            SELECT *, 'Cùng lĩnh vực' as relationship
            FROM documents
            WHERE id != ?
              AND tinh_trang_hieu_luc IN ('Còn hiệu lực', 'Hết hiệu lực một phần')
              AND linh_vuc = ?
            ORDER BY ngay_ban_hanh DESC
            LIMIT 5
        """, (law_id, linh_vuc))
        for r in cursor.fetchall():
            d = dict(r)
            if not any(c['id'] == d['id'] for c in candidates):
                candidates.append(d)

    conn.close()

    # 3. So khớp hiệu lực bằng legal_logic.py
    overlaps = []
    for cand in candidates:
        res = compare_hierarchy(target_doc, cand)
        preferred_id = res["preferred"]["id"]
        
        overlaps.append({
            "doc_id": cand["id"],
            "title": cand["title"],
            "so_ky_hieu": cand.get("so_ky_hieu"),
            "loai_van_ban": cand.get("loai_van_ban"),
            "co_quan_ban_hanh": cand.get("co_quan_ban_hanh"),
            "ngay_ban_hanh": cand.get("ngay_ban_hanh"),
            "tinh_trang_hieu_luc": cand.get("tinh_trang_hieu_luc"),
            "linh_vuc": cand.get("linh_vuc"),
            "relationship": cand.get("relationship", "Cùng lĩnh vực"),
            "preferred": (preferred_id == cand["id"]),
            "reason": res["reason"],
            "clause": res["clause"]
        })

    # Sắp xếp: Ưu tiên các văn bản có quan hệ trực tiếp trước
    overlaps.sort(key=lambda x: 0 if x["relationship"] != "Cùng lĩnh vực" else 1)

    return overlaps
