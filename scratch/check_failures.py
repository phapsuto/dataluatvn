import json
from collections import Counter

with open("scratch/test_300_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

failures = [r for r in data["results"] if r["scoring"]["grade"] in ["WRONG_DOC", "MISS"]]

print(f"Total failures (WRONG_DOC + MISS): {len(failures)} / {data['total_questions']}")
print("\nFailures by type:")
type_counts = Counter(f["question_type"] for f in failures)
for t, count in type_counts.items():
    print(f"Type {t}: {count}")

print("\nDetail of some failures:")
for i, f in enumerate(failures[:15]):
    print(f"\n--- Failure {i+1} (Type {f['question_type']}) ---")
    print(f"Question: {f['question']}")
    print(f"Expected: Doc {f['source']['doc_id']} ({f['source']['so_ky_hieu']}) - {f['source']['article_header']}")
    print(f"Grade: {f['scoring']['grade']}")
    print(f"Details: {f['scoring']['details']}")
    print(f"Routing Level: {f['retrieval']['routing_level']}")
    print(f"Domain: {f['retrieval']['domain']}")
