#!/usr/bin/env python3
"""
scripts/eval_real_model.py
===========================
Script Thử nghiệm Trực tiếp Model AI đã Fine-Tuned LoRA THẬT
từ thư mục models/real_legal_mind_model/
"""

import os
import sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

MODEL_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/models/real_legal_mind_model"
BASE_MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

def eval_real_model():
    print("=" * 70)
    print("🧪 KIỂM THỬ TRỰC TIẾP INFERENCE CỦA MODEL AI LORA FINE-TUNED THẬT 100%")
    print("=" * 70)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"🖥️ Thiết bị suy luận (Inference Device): {device.upper()}")

    print("📥 Loading Tokenizer & Base Model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        torch_dtype=torch.float16 if device == "mps" else torch.float32,
        trust_remote_code=True
    ).to(device)

    print("🔌 Gắn LoRA Adapter Weights thật (models/real_legal_mind_model)...")
    model = PeftModel.from_pretrained(base_model, MODEL_PATH).to(device)
    model.eval()

    messages = [
        {"role": "system", "content": "Bạn là Lan Anh — Trợ lý Pháp lý Thông minh."},
        {"role": "user", "content": "Phân tích đường lối giải quyết tranh chấp bồi thường thiệt hại ngoài hợp đồng về đất đai theo Án lệ và quy định pháp luật Việt Nam?"}
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    print("\n💬 Đang sinh câu trả lời trực tiếp từ neural network weights...")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            top_p=0.9,
            do_sample=True
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    print("=" * 70)
    print("🤖 KẾT QUẢ TRẢ LỜI CỦA MODEL AI LORA THẬT:")
    print("=" * 70)
    print(response)
    print("=" * 70)

if __name__ == "__main__":
    eval_real_model()
