# merge_lora.py

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

snapshot_dir = (
    "./models/flan_t5_base/"
    "models--google--flan-t5-base/"
    "snapshots/7bcac572ce56db69c1ea7c8af255c5d7c9672fc2"
)

lora_dir = "./models/flan_t5_nl2sql_lora"
output_dir = "./models/flan_t5_nl2sql_merged"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(snapshot_dir, use_fast=False)

print("Loading base model...")
base_model = AutoModelForSeq2SeqLM.from_pretrained(
    snapshot_dir,
    torch_dtype=torch.float32,
    device_map="cpu",
    low_cpu_mem_usage=False
)

print("Attaching LoRA...")
model = PeftModel.from_pretrained(
    base_model,
    lora_dir,
    device_map="cpu"
)

print("Merging LoRA weights into base model...")
model = model.merge_and_unload()

print(f"Saving merged model to {output_dir} ...")
model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)

print("DONE Merged model saved.")
