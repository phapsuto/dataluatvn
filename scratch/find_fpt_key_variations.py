import requests

base_key = "sk-038ypse9ISfaKaDOQ9O7STIEbfZZOPBLmJ1v_dwlSmM="

# Let's generate possible variations of characters that are commonly misread:
# Pos 3: '0' -> 'o'
# Pos 10: 'I' -> 'l', '1'
# Pos 16: 'a' -> 'a'
# Pos 23: 'I' -> 'l', '1'
# Pos 29: 'O' -> '0'

variations = []

def generate(current_key, index):
    if index >= len(current_key):
        variations.append(current_key)
        return
        
    char = current_key[index]
    
    # Check if we want to branch at this index
    replacements = []
    if index == 3: # '0'
        replacements = ['0', 'o']
    elif index == 10: # 'I'
        replacements = ['I', 'l', '1']
    elif index == 23: # 'I'
        replacements = ['I', 'l', '1']
    elif index == 29: # 'O'
        replacements = ['O', '0']
    elif index == 42: # 'I' or 'l'
        replacements = ['I', 'l', '1']
        
    if replacements:
        for r in replacements:
            # Reconstruct key with replacement
            new_key = current_key[:index] + r + current_key[index+1:]
            generate(new_key, index + 1)
    else:
        generate(current_key, index + 1)

generate(base_key, 0)
print(f"Generated {len(variations)} variations to test.")

url = "https://mkp-api.fptcloud.com/v1/chat/completions"
payload = {
    "model": "Qwen3-32B",
    "messages": [{"role": "user", "content": "Hi"}],
    "temperature": 0.0
}

success_keys = []

for idx, k in enumerate(variations):
    headers = {
        "Authorization": f"Bearer {k}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        if response.status_code == 200:
            print(f"🎉 SUCCESS: {k}")
            success_keys.append(k)
        else:
            # print(f"Fail {idx}: {k} -> {response.status_code}")
            pass
    except Exception as e:
        print(f"Error {k}: {e}")

if success_keys:
    print(f"Found working keys: {success_keys}")
else:
    print("No working variations found.")
