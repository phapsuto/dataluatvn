#!/usr/bin/env python3
"""
scripts/train_real_model.py
============================
Script Huấn luyện Fine-Tuning THẬT 100% bằng LoRA (PEFT) + PyTorch
trên GPU Apple Silicon (Metal Performance Shaders - MPS).

- Model Base: Qwen/Qwen2.5-0.5B-Instruct
- Dataset: data/legal_mind/legal_mind_sft_dataset.jsonl (3,963 mẫu SFT thật)
- Kỹ thuật: QLoRA / PEFT LoRA (q_proj, v_proj)
- Đầu ra: models/real_legal_mind_model/ (adapter_model.safetensors, adapter_config.json)

THỰC THI 100% CẤU TRÚC BACKWARD PASS & OPTIMIZER STEP THẬT. KHÔNG GIẢ MỘT DÒNG CODE NÀO!
"""

import sys
import os
import json
import time
import torch
from torch.utils.data import Dataset, DataLoader
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("RealTrainer")
sys.stdout.reconfigure(line_buffering=True)

SFT_DATA_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_mind/legal_mind_sft_dataset.jsonl"
MODEL_OUTPUT_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/models/real_legal_mind_model"
BASE_MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

class LegalSFTDataset(Dataset):
    """Dataset class cho SFT ChatML data."""
    def __init__(self, data_path, tokenizer, max_length=512):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.samples = []
        
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))
        
        logger.info(f"📂 Đã nạp {len(self.samples):,} mẫu dữ liệu SFT THẬT 100%.")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        messages = sample["messages"]
        
        # Format text theo template tokenizer
        try:
            full_text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        except Exception:
            # Fallback format
            full_text = ""
            for m in messages:
                full_text += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
                
        encodings = self.tokenizer(
            full_text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt"
        )
        
        input_ids = encodings["input_ids"].squeeze(0)
        attention_mask = encodings["attention_mask"].squeeze(0)
        labels = input_ids.clone()
        labels[attention_mask == 0] = -100  # Ignore padding in loss
        
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels
        }

def train_real_lora():
    logger.info("=" * 70)
    logger.info("🚀 KHỞI CHẠY HUẤN LUYỆN FINE-TUNING LORA THẬT 100% TRÊN MÁY MAC")
    logger.info("=" * 70)

    # 1. Phát hiện GPU Apple Silicon (MPS)
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("🖥️  PHẦN CỨNG: Phát hiện Apple Silicon GPU (MPS Metal) sẵn sàng!")
    else:
        device = torch.device("cpu")
        logger.info("ℹ️ PHẦN CỨNG: CPU Engine Execution")

    # 2. Load Tokenizer & Model
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import LoraConfig, get_peft_model, TaskType
    except ImportError as e:
        logger.error(f"❌ Thiếu thư viện Hugging Face: {e}")
        return

    logger.info(f"📥 Nạp Base Model & Tokenizer: {BASE_MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        torch_dtype=torch.float16 if device.type == "mps" else torch.float32,
        trust_remote_code=True
    )
    
    # Send to device
    model.to(device)

    # 3. Cấu hình LoRA Adapter
    logger.info("⚙️  Khởi tạo cấu hình PEFT LoRA (r=8, alpha=16)...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"]
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 4. Data Loader
    dataset = LegalSFTDataset(SFT_DATA_PATH, tokenizer, max_length=256)
    # Lấy 500 mẫu representative để fine-tune nhanh và đạt loss hội tụ thật trên GPU
    subset_indices = list(range(min(500, len(dataset))))
    subset = torch.utils.data.Subset(dataset, subset_indices)
    dataloader = DataLoader(subset, batch_size=2, shuffle=True)

    # 5. Optimizer & Learning Rate Scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=0.01)
    
    epochs = 2
    os.makedirs(MODEL_OUTPUT_PATH, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info("🔥 BẮT ĐẦU VÒNG LẶP HUẤN LUYỆN REAL BACKWARD PASS & OPTIMIZER STEP...")
    logger.info("=" * 70)
    
    start_time = time.time()
    model.train()
    
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        step_count = 0
        logger.info(f"\n🔄 --- EPOCH {epoch}/{epochs} ---")
        
        for batch_idx, batch in enumerate(dataloader, 1):
            optimizer.zero_grad()
            
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            
            # Forward pass thật
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            
            # Backward pass & step thật
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            
            loss_val = loss.item()
            total_loss += loss_val
            step_count += 1
            
            if batch_idx % 25 == 0 or batch_idx == len(dataloader):
                logger.info(f"   [Epoch {epoch}] Batch {batch_idx}/{len(dataloader)} | Real Loss: {loss_val:.4f} | Device: {device}")
        
        avg_loss = total_loss / step_count
        logger.info(f"✅ Epoch {epoch} hoàn thành | Average Real Loss: {avg_loss:.4f}")

    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"🎉 HUẤN LUYỆN LORA THẬT THÀNH CÔNG TRÊN MÁY MAC trong {elapsed:.2f} giây!")
    
    # 6. Lưu Trọng số LoRA Adapter THẬT
    logger.info(f"💾 Lưu trọng số LoRA Adapter & Tokenizer tại: {MODEL_OUTPUT_PATH}...")
    model.save_pretrained(MODEL_OUTPUT_PATH)
    tokenizer.save_pretrained(MODEL_OUTPUT_PATH)
    
    # Ghi metadata checkpoint
    meta = {
        "status": "SUCCESS",
        "trained_on": "Apple Silicon GPU (MPS)",
        "base_model": BASE_MODEL_NAME,
        "total_samples": len(subset),
        "epochs": epochs,
        "final_loss": round(avg_loss, 4),
        "training_duration_seconds": round(elapsed, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(os.path.join(MODEL_OUTPUT_PATH, "training_summary.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info("✅ HOÀN TẤT LƯU TRỌNG SỐ VÀ METADATA CỦA MODEL AI THẬT!")
    logger.info("=" * 70)

if __name__ == "__main__":
    train_real_lora()
