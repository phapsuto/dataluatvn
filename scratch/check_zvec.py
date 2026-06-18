import os
import sys
import zvec

# Add parent dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import ZVEC_DB_PATH

def main():
    print(f"Opening Zvec collection at {ZVEC_DB_PATH}...")
    try:
        collection = zvec.open(path=ZVEC_DB_PATH)
        
        # Let's print collection info
        print("Collection schema:")
        print("Name:", collection.schema.name)
        print("Fields:", [f.name for f in collection.schema.fields])
        print("Vectors:", [v.name for v in collection.schema.vectors])
        
        dummy_vector = [0.0] * 1024
        
        print("\nPerforming dummy vector search to inspect top results...")
        results = collection.query(
            queries=zvec.Query(field_name="dense_vector", vector=dummy_vector),
            topk=10
        )
        
        print(f"Found {len(results)} query results:")
        found_target = False
        for i, res in enumerate(results):
            fields = res.fields
            doc_id = fields.get("doc_id")
            so_ky_hieu = fields.get("so_ky_hieu")
            chunk_text = fields.get("chunk_text", "")
            print(f"[{i+1}] ID={res.id}, doc_id={doc_id}, so_ky_hieu='{so_ky_hieu}', score={res.score:.6f}")
            print(f"    Text: {chunk_text[:150]}...")
            if str(doc_id) == "187959" or doc_id == 187959:
                found_target = True
                
        if found_target:
            print("\n✅ Verification SUCCESS: doc_id 187959 exists in Zvec!")
        else:
            print("\n⚠️ Note: doc_id 187959 was not in the top 10 dummy search results. This is expected since the search is based on distance. Let's query with a filter specifically for doc_id.")
            # Let's run a query filtered to doc_id = 187959
            try:
                print("Trying to filter query by doc_id = 187959...")
                filtered_res = collection.query(
                    queries=zvec.Query(field_name="dense_vector", vector=dummy_vector),
                    filter="doc_id = 187959",
                    topk=5
                )
                print(f"Filter query found {len(filtered_res)} chunks:")
                for i, res in enumerate(filtered_res):
                    fields = res.fields
                    print(f"  - Chunk UID={res.id}, doc_id={fields.get('doc_id')}, so_ky_hieu='{fields.get('so_ky_hieu')}'")
                if filtered_res:
                    print("✅ Verification SUCCESS: doc_id 187959 found via filter query!")
                else:
                    print("❌ Verification FAILED: doc_id 187959 not found in Zvec!")
            except Exception as e:
                print(f"Filter query failed: {e}")
                
    except Exception as e:
        print(f"❌ Error opening or querying Zvec: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
