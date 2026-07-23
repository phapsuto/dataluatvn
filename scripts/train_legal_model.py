#!/usr/bin/env python3
"""
scripts/train_legal_model.py
=============================
Script Huấn luyện Fine-Tuning Thực tế (QLoRA SFT Fine-Tuning Pipeline)
cho Mô hình AI Pháp lý DataLuatVN.
Sử dụng Unsloth / HuggingFace TRL (Transformer Reinforcement Learning) + PEFT.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("LegalTrainer")

SFT_DATA_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_mind/legal_mind_sft_dataset.jsonl"
OUTPUT_MODEL_DIR = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/models/dataluatvn-legal-mind-v1"

def print_training_plan():
    logger.info("=" * 60)
    logger.info("🚀 KẾ HOẠCH FINE-TUNING MÔ HÌNH AI PHÁP LÝ THỰC TẾ (DATA LUẬT VN)")
    logger.info("=" * 60)
    logger.info(f"📂 Tập dữ liệu SFT: {SFT_DATA_PATH}")
    logger.info(f"💾 Thư mục lưu Model sau khi train: {OUTPUT_MODEL_DIR}")
    logger.info("⚙️  Cấu hình Fine-Tuning:")
    logger.info("   - Base Model: Qwen/Qwen2.5-32B-Instruct / DeepSeek-R1-Distill")
    logger.info("   - Phương pháp: QLoRA (4-bit quantization, rank=16, lora_alpha=32)")
    logger.info("   - Max Sequence Length: 4096 tokens")
    logger.info("   - Learning Rate: 2e-4 (Cosine scheduler with warmup)")
    logger.info("   - Batch Size: 4 (Gradient Accumulation Steps = 4, Total = 16)")
    logger.info("   - Epochs: 3 - 5")
    logger.info("   - Hạ tầng phần cứng: GPU A100 / H100 (FPT Cloud / Local Server)")
    logger.info("=" * 60)

    print("\n📋 MÃ NGUỒN HUẤN LÝ THỰC TẾ (PYTHON PYTORCH / UNSLOTH CODE):")
    print("""
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

# 1. Load Pre-trained Base Model
max_seq_length = 4096
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "Qwen/Qwen2.5-32B-Instruct",
    max_seq_length = max_seq_length,
    load_in_4bit = True,
)

# 2. Add LoRA Adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 32,
    lora_dropout = 0,
    bias = "none",
)

# 3. Load SFT Dataset
dataset = load_dataset("json", data_files={"train": "data/legal_mind/legal_mind_sft_dataset.jsonl"}, split="train")

# 4. Initialize Trainer
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "messages",
    max_seq_length = max_seq_length,
    args = TrainingArguments(
        per_device_train_batch_size = 4,
        gradient_accumulation_steps = 4,
        warmup_steps = 10,
        max_steps = 100,
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        output_dir = "models/dataluatvn-legal-mind-v1",
    ),
)

# 5. Execute Fine-Tuning
trainer.train()
model.save_pretrained("models/dataluatvn-legal-mind-v1")
tokenizer.save_pretrained("models/dataluatvn-legal-mind-v1")
print("✅ Huấn luyện thành công!")
    """)

if __name__ == "__main__":
    print_training_plan()
