# flan_t5_base

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

model_name = "google/flan-t5-base"

AutoModelForSeq2SeqLM.from_pretrained(
    model_name,
    cache_dir="./models/flan_t5_base"
)

AutoTokenizer.from_pretrained(
    model_name,
    cache_dir="./models/flan_t5_base"
)