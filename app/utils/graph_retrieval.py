import sqlite3
import os
from typing import List, Dict, Any, Tuple
from app.database import get_db_connection

# Constants for legal authority ranking
AUTHORITY_WEIGHTS = {
    "hiến pháp": 1.0,
    "bộ luật": 0.9,
    "luật": 0.9,
    "pháp lệnh": 0.8,
    "nghị định": 0.7,
    "nghị quyết": 0.6,
    "quyết định": 0.6,
    "thông tư": 0.5,
    "văn bản địa phương": 0.3,
    "default": 0.4
}

# Constants for relationship weights
RELATIONSHIP_WEIGHTS = {
    "thay thế": 1.0,
    "bị thay thế bởi": 1.0,
    "thay thế cho": 1.0,
    "sửa đổi bổ sung": 0.9,
    "được sửa đổi bổ sung": 0.9,
    "hướng dẫn": 0.7,
    "được hướng dẫn": 0.7,
    "quy định chi tiết": 0.7,
    "được quy định chi tiết": 0.7,
    "căn cứ": 0.5,
    "liên quan": 0.3,
    "default": 0.3
}

def get_authority_score(loai_van_ban: str) -> float:
    """Returns the legal hierarchy score for a document type."""
    if not loai_van_ban:
        return AUTHORITY_WEIGHTS["default"]
    
    loai_lower = loai_van_ban.lower().strip()
    for key, weight in AUTHORITY_WEIGHTS.items():
        if key in loai_lower:
            return weight
    return AUTHORITY_WEIGHTS["default"]

def get_relationship_weight(relationship: str) -> float:
    """Returns the strength weight for a legal connection type."""
    if not relationship:
        return RELATIONSHIP_WEIGHTS["default"]
    
    rel_lower = relationship.lower().strip()
    for key, weight in RELATIONSHIP_WEIGHTS.items():
        if key in rel_lower:
            return weight
    return RELATIONSHIP_WEIGHTS["default"]

def graph_expand_results(
    initial_candidates: List[Dict[str, Any]], 
    query: str = "", 
    hops: int = 1,
    max_nodes: int = 30
) -> List[Dict[str, Any]]:
    """
    Expands a seed set of documents using 1-hop or 2-hop traversal over the legal relationships graph.
    Applies PPR-lite scoring combining relevance similarity, relationship weights, and authority hierarchy.
    
    Args:
        initial_candidates: List of Dict containing at least {"doc_id": int, "score": float} from the base search.
        query: User question (optional).
        hops: Number of traversal steps (default: 1).
        max_nodes: Maximum number of final nodes to return.
        
    Returns:
        Sorted list of Dict containing expanded candidate document details with updated scores.
    """
    if not initial_candidates:
        return []
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Track nodes in the graph: doc_id -> {details}
    graph_nodes = {}
    
    # Phase A: Load initial seeds into the node pool
    seed_ids = []
    for item in initial_candidates:
        doc_id = item["doc_id"]
        score = item.get("score") or 0.0
        
        # Fetch metadata of the seed document
        cursor.execute("""
            SELECT id, title, so_ky_hieu, loai_van_ban, tinh_trang_hieu_luc, ngay_ban_hanh
            FROM documents WHERE id = ?
        """, (doc_id,))
        row = cursor.fetchone()
        if row:
            doc_info = dict(row)
            doc_info["similarity_score"] = score
            doc_info["relationship_weight"] = 0.0  # Seeds have no relation weight initially
            doc_info["is_seed"] = True
            graph_nodes[doc_id] = doc_info
            seed_ids.append(doc_id)
            
    # Phase B: Perform Graph Expansion (Hops)
    current_layer = set(seed_ids)
    visited_edges = set()
    
    for hop in range(hops):
        next_layer = set()
        if not current_layer:
            break
            
        placeholders = ",".join(["?"] * len(current_layer))
        query_sql = f"""
            SELECT r.doc_id, r.other_doc_id, r.relationship,
                   d.id as dest_id, d.title, d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc, d.ngay_ban_hanh
            FROM relationships r
            JOIN documents d ON (r.other_doc_id = d.id AND r.doc_id IN ({placeholders}))
            UNION
            SELECT r.doc_id, r.other_doc_id, r.relationship,
                   d.id as dest_id, d.title, d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc, d.ngay_ban_hanh
            FROM relationships r
            JOIN documents d ON (r.doc_id = d.id AND r.other_doc_id IN ({placeholders}))
        """
        
        # Prepare parameters for UNION query (current_layer IDs twice)
        params = list(current_layer) + list(current_layer)
        try:
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
        except Exception as e:
            print(f"⚠️ Error querying relationships in Graph Expansion: {e}")
            break
            
        for row in rows:
            # Identify source node (the one in our current layer) and destination node
            doc_id = row["doc_id"]
            other_doc_id = row["other_doc_id"]
            rel_type = row["relationship"]
            dest_id = row["dest_id"]
            
            # Avoid processing duplicate edges
            edge_key = tuple(sorted([doc_id, other_doc_id]) + [rel_type])
            if edge_key in visited_edges:
                continue
            visited_edges.add(edge_key)
            
            # Source of the edge must be in our node pool
            source_id = doc_id if doc_id in graph_nodes else other_doc_id
            if source_id not in graph_nodes:
                continue
                
            source_node = graph_nodes[source_id]
            rel_weight = get_relationship_weight(rel_type)
            
            # If destination is not in our pool yet, create it
            if dest_id not in graph_nodes:
                dest_info = {
                    "id": dest_id,
                    "title": row["title"],
                    "so_ky_hieu": row["so_ky_hieu"],
                    "loai_van_ban": row["loai_van_ban"],
                    "tinh_trang_hieu_luc": row["tinh_trang_hieu_luc"],
                    "ngay_ban_hanh": row["ngay_ban_hanh"],
                    "similarity_score": source_node["similarity_score"] * 0.5, # Decay factor
                    "relationship_weight": rel_weight,
                    "is_seed": False
                }
                graph_nodes[dest_id] = dest_info
                next_layer.add(dest_id)
            else:
                # Node already exists. Update its relationship weight to the maximum path found
                existing_node = graph_nodes[dest_id]
                if rel_weight > existing_node["relationship_weight"]:
                    existing_node["relationship_weight"] = rel_weight
                    
        current_layer = next_layer
        
    conn.close()
    
    # Phase C: PPR-Lite Scoring & Effectiveness Filtering
    final_candidates = []
    
    for doc_id, node in graph_nodes.items():
        status = (node.get("tinh_trang_hieu_luc") or "").lower()
        
        # 1. Filter out expired documents to avoid serving outdated laws
        # EXCEPTION: If the document is expired but is a seed (user searched it directly)
        # or it has a replacement connection, we keep it for context tracking.
        is_expired = "hết hiệu lực" in status and "một phần" not in status
        if is_expired and not node.get("is_seed") and node["relationship_weight"] < 1.0:
            continue
            
        # 2. PPR-Lite calculation
        sim_score = node["similarity_score"]
        rel_weight = node["relationship_weight"]
        auth_score = get_authority_score(node.get("loai_van_ban"))
        
        # Normalized formula
        ppr_score = (sim_score * 0.6) + (rel_weight * 0.3) + (auth_score * 0.1)
        node["score"] = ppr_score
        
        final_candidates.append(node)
        
    # Sort candidates by final PPR-lite score descending
    sorted_candidates = sorted(final_candidates, key=lambda x: x["score"], reverse=True)
    
    return sorted_candidates[:max_nodes]
