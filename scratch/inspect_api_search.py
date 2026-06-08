import requests

def test():
    base_url = "http://localhost:2004"
    api_key = "dlvn_portal_default_key"
    
    # 1. Search with only province_code = 01
    print("1. Searching with province_code = 01...")
    r = requests.get(f"{base_url}/laws/search?province_code=01&api_key={api_key}&limit=5&require_content=true")
    res = r.json()
    print("Total results:", res["total"])
    for d in res["results"]:
        print(f"  ID: {d['id']}, Title: {d['title'][:60]}, Agency: {d['co_quan_ban_hanh']}")
        
    # 2. Search with province_code = 01 and ward_code = 00004
    print("\n2. Searching with province_code = 01 and ward_code = 00004...")
    r = requests.get(f"{base_url}/laws/search?province_code=01&ward_code=00004&api_key={api_key}&limit=5&require_content=true")
    res = r.json()
    print("Total results:", res["total"])
    for d in res["results"]:
        print(f"  ID: {d['id']}, Title: {d['title'][:60]}, Agency: {d['co_quan_ban_hanh']}")

if __name__ == "__main__":
    test()
