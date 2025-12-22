# flan_sql_local.py
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import os


class FlanSQLLLM:
    def __init__(self):
        self.model_dir = "./models/flan_t5_nl2sql_merged"

        if not os.path.isdir(self.model_dir):
            raise FileNotFoundError(f"Merged model not found: {self.model_dir}")

        torch.set_grad_enabled(False)

        # Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_dir,
            use_fast=False
        )

        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.model_dir,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=False
        )

        # Force model to have REAL CPU weights
        self.model.to("cpu")
        self.model.eval()

        print("\n==============================")
        print(" FLAN + LoRA loaded on CPU")
        print(" No accelerate, no meta tensors")
        print("==============================\n")

    def generate(self, prompt: str, max_new_tokens: int = 128) -> str:
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True
        )

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=4
            )

        return self.tokenizer.decode(
            outputs[0],
            skip_special_tokens=True
        ).strip()
