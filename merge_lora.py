import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

base_dir = "model/models/flan_t5_base"          
lora_dir = "nl2sql-lora-trained"               
output_dir = "models/flan_t5_nl2sql_merged"     

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    base_dir,
    use_fast=False,
    local_files_only=True
)

print("Loading base model...")
base_model = AutoModelForSeq2SeqLM.from_pretrained(
    base_dir,
    torch_dtype=torch.float32,
    local_files_only=True
)

print("Attaching LoRA...")
model = PeftModel.from_pretrained(
    base_model,
    lora_dir,
    local_files_only=True
)

print("Merging LoRA weights into base model...")
model = model.merge_and_unload()

print(f"Saving merged model to {output_dir} ...")
model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)

print("DONE Merged model saved.")
