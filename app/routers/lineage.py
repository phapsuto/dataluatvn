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
    size: Optional[int] = None

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
        "value": 30 if is_target else 20,
        "size": 26 if is_target else 15
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
    Truy vấn thông minh và tối ưu hóa kết nối để xây dựng mạng lưới quan hệ (lineage) của văn bản.
    Đầu ra chuẩn hóa danh sách `nodes` và `edges` để nạp trực tiếp vào thư viện `vis-network`.
    
    Tối ưu hóa:
    - Sắp xếp và lọc các nút liên kết trực tiếp theo độ quan trọng pháp lý.
    - Tìm kiếm 2-hop có chọn lọc nếu tổng số nút nhỏ (<15) để mở rộng đồ thị phong phú.
    - Truy vấn đồ thị con (subgraph query) để hiển thị tất cả các mối quan hệ giữa các nút trong đồ thị.
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

    # Thu thập tất cả các ID liên quan trực tiếp (neighbors)
    neighbor_ids = set()
    for r in direct_rels:
        neighbor_ids.add(r['doc_id'])
        neighbor_ids.add(r['other_doc_id'])
    neighbor_ids.discard(law_id)

    # 3. Lấy metadata của các neighbor để xếp hạng độ quan trọng
    neighbors_meta = {}
    if neighbor_ids:
        placeholders = ",".join(["?"] * len(neighbor_ids))
        cursor.execute(f"""
            SELECT id, loai_van_ban, co_quan_ban_hanh, so_ky_hieu, ngay_ban_hanh, title, tinh_trang_hieu_luc 
            FROM documents 
            WHERE id IN ({placeholders})
        """, list(neighbor_ids))
        for row in cursor.fetchall():
            d = dict(row)
            neighbors_meta[d["id"]] = d

    # Định nghĩa trọng số mối quan hệ
    def get_relationship_weight(rel_str: str) -> int:
        r = rel_str.lower()
        if any(x in r for x in ["thay thế", "sửa đổi", "bổ sung", "hết hiệu lực", "đình chỉ"]):
            return 50  # Quan hệ thay đổi hiệu lực
        if any(x in r for x in ["căn cứ", "hướng dẫn", "hd, qđ"]):
            return 30  # Quan hệ phân cấp
        if "dẫn chiếu" in r:
            return 10  # Quan hệ dẫn chiếu thông thường
        return 5

    # Định nghĩa trọng số cấp bậc loại văn bản
    def get_document_rank_weight(loai_vb: str) -> int:
        l = (loai_vb or "").strip().lower()
        if "hiến pháp" in l:
            return 20
        if l in ["bộ luật", "luật"]:
            return 18
        if l == "pháp lệnh":
            return 15
        if l == "nghị định":
            return 12
        if l == "quyết định":
            return 8
        if "thông tư" in l:
            return 6
        return 2

    # Tính điểm quan trọng của từng neighbor
    neighbor_scores = {}
    for r in direct_rels:
        nid = r['doc_id'] if r['other_doc_id'] == law_id else r['other_doc_id']
        rel_weight = get_relationship_weight(r['relationship'])
        
        meta = neighbors_meta.get(nid, {})
        rank_weight = get_document_rank_weight(meta.get("loai_van_ban") or "")
        
        score = rel_weight + rank_weight
        # Lưu điểm số cao nhất nếu có nhiều quan hệ
        neighbor_scores[nid] = max(neighbor_scores.get(nid, 0), score)

    # Sắp xếp neighbors theo điểm số giảm dần
    sorted_neighbors = sorted(neighbor_scores.keys(), key=lambda x: neighbor_scores[x], reverse=True)

    # Giới hạn số lượng neighbors trực tiếp tối đa là 40 để tránh rối mắt
    selected_neighbors = sorted_neighbors[:40]
    final_node_ids = {law_id} | set(selected_neighbors)

    # 4. Nếu số lượng node nhỏ (< 15), mở rộng thêm 2-hop cho các neighbors quan trọng nhất
    if len(final_node_ids) < 15 and selected_neighbors:
        # Lấy tối đa 5 neighbors hàng đầu để mở rộng 2-hop
        nodes_to_expand = selected_neighbors[:5]
        placeholders = ",".join(["?"] * len(nodes_to_expand))
        
        cursor.execute(f"""
            SELECT doc_id, other_doc_id, relationship 
            FROM relationships 
            WHERE (doc_id IN ({placeholders}) OR other_doc_id IN ({placeholders}))
              AND doc_id != ? AND other_doc_id != ?
            LIMIT 50
        """, nodes_to_expand + nodes_to_expand + [law_id, law_id])
        
        extra_rels = [dict(row) for row in cursor.fetchall()]
        
        # Thêm các node 2-hop (chỉ lấy thêm tối đa 15 node mới để tránh quá tải)
        added_2hop = 0
        for er in extra_rels:
            for nid in [er['doc_id'], er['other_doc_id']]:
                if nid not in final_node_ids and added_2hop < 15:
                    final_node_ids.add(nid)
                    added_2hop += 1

    # 5. TRUY VẤN SUBGRAPH: Lấy toàn bộ mối quan hệ ngang/dọc giữa tất cả các node trong đồ thị hiện tại
    final_node_list = list(final_node_ids)
    if not final_node_list:
        conn.close()
        return {"nodes": [], "edges": []}

    placeholders = ",".join(["?"] * len(final_node_list))
    cursor.execute(f"""
        SELECT doc_id, other_doc_id, relationship 
        FROM relationships 
        WHERE doc_id IN ({placeholders}) AND other_doc_id IN ({placeholders})
    """, final_node_list + final_node_list)
    all_subgraph_rels = [dict(row) for row in cursor.fetchall()]

    # Lấy metadata đầy đủ cho toàn bộ node (bao gồm cả các node 2-hop vừa được thêm)
    cursor.execute(f"SELECT * FROM documents WHERE id IN ({placeholders})", final_node_list)
    nodes_rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # 6. Biến đổi dữ liệu sang định dạng vis-network
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
            "size": style["size"],  # Kích thước node trực tiếp
            "font": {
                "size": 13,
                "color": "#ffffff",
                "face": "Segoe UI, Inter, sans-serif",
                "strokeWidth": 3,
                "strokeColor": "rgba(0,0,0,0.6)"
            }
        })

    # Deduplicate relationships to prevent duplicate edges
    seen_edges = set()
    edges = []
    for r in all_subgraph_rels:
        # Chỉ giữ lại các quan hệ mà cả 2 node đều nằm trong danh sách cuối cùng
        if r['doc_id'] in final_node_ids and r['other_doc_id'] in final_node_ids:
            # Sắp xếp và định danh edge để tránh trùng lặp
            edge_key = (r['doc_id'], r['other_doc_id'], r['relationship'])
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

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
