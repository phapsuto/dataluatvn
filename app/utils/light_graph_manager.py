import sqlite3
import re
import os
from typing import List, Dict, Any, Tuple, Set
from app.database import get_db_connection
from app.utils.llm_gateway import LLMGateway

GRAPH_DB_PATH = "light_graph_store.db"

class LightGraphManager:
    @staticmethod
    def init_db():
        """Khởi tạo cơ sở dữ liệu đồ thị tri thức SQLite."""
        conn = sqlite3.connect(GRAPH_DB_PATH)
        cursor = conn.cursor()
        
        # Bảng lưu trữ các nút (Nodes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,      -- 'law', 'concept', 'agency', 'penalty'
                name TEXT NOT NULL,
                description TEXT
            )
        """)
        
        # Bảng lưu trữ các cạnh (Edges/Relationships)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT,
                target TEXT,
                relation TEXT NOT NULL,  -- 'guides', 'amends', 'defines', 'enforces'
                weight REAL DEFAULT 1.0,
                PRIMARY KEY (source, target, relation),
                FOREIGN KEY (source) REFERENCES graph_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target) REFERENCES graph_nodes(id) ON DELETE CASCADE
            )
        """)
        
        # Tạo index tăng tốc truy vấn đồ thị
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target)")
        
        conn.commit()
        conn.close()

    @staticmethod
    def add_node(node_id: str, node_type: str, name: str, description: str = ""):
        conn = sqlite3.connect(GRAPH_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO graph_nodes (id, type, name, description)
            VALUES (?, ?, ?, ?)
        """, (node_id, node_type, name, description))
        conn.commit()
        conn.close()

    @staticmethod
    def add_edge(source: str, target: str, relation: str, weight: float = 1.0):
        if source == target:
            return  # Tránh tự nối chính mình
        conn = sqlite3.connect(GRAPH_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO graph_edges (source, target, relation, weight)
            VALUES (?, ?, ?, ?)
        """, (source, target, relation, weight))
        conn.commit()
        conn.close()

    @staticmethod
    def extract_legal_entities(text: str, so_ky_hieu: str = "") -> List[Tuple[str, str, str]]:
        """
        Trích xuất thực thể pháp luật dựa trên các mẫu Rule-based kết hợp Regex.
        Trả về danh sách Tuple: (entity_id, entity_type, entity_name)
        """
        entities = []
        
        # 1. Trích xuất Cơ quan ban hành (Agencies)
        agencies_patterns = {
            "Quốc hội": r"(Quốc\s+hội|QH)",
            "Chính phủ": r"(Chính\s+phủ|CP)",
            "Thủ tướng Chính phủ": r"(Thủ\s+tướng|TTg)",
            "Bộ Lao động - Thương binh và Xã hội": r"(Bộ\s+Lao\s+động\s*\-\s*Thương\s+binh\s+và\s+Xã\s+hội|LĐTBXH)",
            "Bộ Tài chính": r"(Bộ\s+Tài\s+chính|BTC)",
            "Bộ Công an": r"(Bộ\s+Công\s+an|BCA)",
            "Bộ Tư pháp": r"(Bộ\s+Tư\s+pháp|BTP)",
            "Tòa án nhân dân tối cao": r"(Tòa\s+án\s+nhân\s+dân\s+tối\s+cao|TANDTC)"
        }
        
        for name, pattern in agencies_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                ent_id = f"AGENCY_{name.replace(' ', '_')}"
                entities.append((ent_id, "agency", name))

        # 2. Trích xuất trích dẫn văn bản pháp luật khác (Cross-references)
        # Ví dụ: Luật Đất đai, Bộ luật Lao động, Luật số 45/2019/QH14, Nghị định số 145/2020/NĐ-CP
        law_ref_pattern = re.compile(
            r"(Bộ\s+luật|Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?(\d+/\d+/[A-Z0-9\-]+)", 
            re.IGNORECASE
        )
        for match in law_ref_pattern.find_all(text) if hasattr(law_ref_pattern, "find_all") else law_ref_pattern.findall(text):
            doc_type, _, doc_code = match
            ent_id = f"LAW_{doc_code.replace('/', '_')}"
            ent_name = f"{doc_type} {doc_code}"
            entities.append((ent_id, "law", ent_name))

        # 3. Trích xuất các khái niệm luật phổ biến (Concepts)
        concepts = {
            "hợp đồng lao động": r"hợp\s+đồng\s+lao\s+động",
            "thử việc": r"thử\s+việc",
            "sa thải": r"sa\s+thải",
            "bảo hiểm xã hội": r"bảo\s+hiểm\s+xã\s+hội",
            "thuế thu nhập cá nhân": r"thuế\s+thu\s+nhập\s+cá\s+nhân",
            "sổ đỏ": r"(sổ\s+đỏ|giấy\s+chứng\s+nhận\s+quyền\s+sử\s+dụng\s+đất)",
            "tranh chấp đất đai": r"tranh\s+chấp\s+đất\s+đai",
            "án lệ": r"án\s+lệ"
        }
        for name, pattern in concepts.items():
            if re.search(pattern, text, re.IGNORECASE):
                ent_id = f"CONCEPT_{name.replace(' ', '_')}"
                entities.append((ent_id, "concept", name.capitalize()))

        return list(set(entities))

    @classmethod
    def index_document_graph(cls, doc_id: int, title: str, so_ky_hieu: str, content_text: str):
        """Đánh chỉ mục đồ thị gia tăng cho một văn bản cụ thể."""
        cls.init_db()
        
        # 1. Tạo nút đại diện cho Văn bản Luật này
        doc_node_id = f"LAW_ID_{doc_id}"
        cls.add_node(doc_node_id, "law", so_ky_hieu or title[:50], title)

        # 2. Trích xuất các thực thể trong văn bản
        entities = cls.extract_legal_entities(content_text, so_ky_hieu)
        
        for ent_id, ent_type, ent_name in entities:
            # Lưu thực thể đó vào Graph Nodes
            cls.add_node(ent_id, ent_type, ent_name)
            
            # Tạo liên kết từ Văn bản Luật sang Thực thể đó
            cls.add_edge(doc_node_id, ent_id, "references")

        # 3. Khai thác mối quan hệ liên kết chéo từ SQLite chính để đưa vào Đồ thị
        try:
            m_conn = get_db_connection()
            m_cursor = m_conn.cursor()
            m_cursor.execute("""
                SELECT other_doc_id, relationship 
                FROM relationships 
                WHERE doc_id = ?
            """, (doc_id,))
            rels = m_cursor.fetchall()
            m_conn.close()
            
            for other_id, rel_type in rels:
                other_node_id = f"LAW_ID_{other_id}"
                # Định nghĩa quan hệ
                # Ví dụ: "hướng dẫn thi hành" -> guides, "sửa đổi" -> amends
                clean_rel = "references"
                if "hướng dẫn" in rel_type:
                    clean_rel = "guides"
                elif "sửa đổi" in rel_type or "bổ sung" in rel_type:
                    clean_rel = "amends"
                elif "thay thế" in rel_type:
                    clean_rel = "replaces"
                    
                cls.add_edge(doc_node_id, other_node_id, clean_rel)
        except Exception as e:
            print(f"⚠️ Warning: Failed to load crosslink relationships for graph indexing: {e}")

    @staticmethod
    def query_graph_connections(seed_doc_ids: List[int], max_depth: int = 2) -> Set[int]:
        """
        Duyệt đồ thị từ danh sách văn bản nguồn (seed_doc_ids) qua max_depth bước
        để lấy ra ID của các văn bản có quan hệ liên kết mật thiết nhất.
        """
        if not seed_doc_ids:
            return set()
            
        conn = sqlite3.connect(GRAPH_DB_PATH)
        cursor = conn.cursor()
        
        visited = set(f"LAW_ID_{id}" for id in seed_doc_ids)
        queue = list(visited)
        
        # Duyệt BFS đồ thị
        for depth in range(max_depth):
            next_queue = []
            if not queue:
                break
                
            # Batch query to avoid "too many SQL variables" (limit of 999 parameters in SQLite)
            neighbors = []
            queue_list = list(queue)
            batch_size = 250
            for i in range(0, len(queue_list), batch_size):
                chunk = queue_list[i : i + batch_size]
                placeholders = ",".join(["?"] * len(chunk))
                query = f"""
                    SELECT target FROM graph_edges WHERE source IN ({placeholders}) AND target LIKE 'LAW_ID_%'
                    UNION
                    SELECT source FROM graph_edges WHERE target IN ({placeholders}) AND source LIKE 'LAW_ID_%'
                """
                try:
                    cursor.execute(query, chunk + chunk)
                    neighbors.extend([row[0] for row in cursor.fetchall()])
                except Exception:
                    pass
            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    next_queue.append(n)
            queue = next_queue
            
        conn.close()
        
        # Trích xuất lại ID dạng số nguyên
        connected_ids = set()
        for node_id in visited:
            if node_id.startswith("LAW_ID_"):
                try:
                    connected_ids.add(int(node_id.replace("LAW_ID_", "")))
                except ValueError:
                    pass
        return connected_ids
