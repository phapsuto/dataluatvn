import os
import sys
import faiss
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import FAISS_INDEX_SOTA

def main():
    print(f"Reading FAISS index from {FAISS_INDEX_SOTA}...")
    try:
        index = faiss.read_index(FAISS_INDEX_SOTA)
        print(f"Index loaded successfully. Total vectors (ntotal): {index.ntotal}")
        
        # Check if ID Map exists and print its class
        print(f"Index class: {type(index)}")
        
        if hasattr(index, 'id_map'):
            id_map_vector = faiss.vector_to_array(index.id_map)
            print("Successfully retrieved id_map array.")
            print(f"id_map length: {len(id_map_vector)}")
            
            target_ids = [1553772, 1553773, 1553774, 1553775]
            for tid in target_ids:
                if tid in id_map_vector:
                    idx = np.where(id_map_vector == tid)[0][0]
                    print(f"✅ ID {tid} found in id_map at position {idx}!")
                else:
                    print(f"❌ ID {tid} NOT found in id_map.")
        else:
            print("Index does not have 'id_map' attribute directly.")
            
    except Exception as e:
        print(f"❌ Error loading or checking FAISS index: {e}")

if __name__ == "__main__":
    main()
