from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MODEL_ID = "google/flan-t5-base"
SAVE_PATH = "./models/flan_t5_base"

print("Downloading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

print("Downloading model...")
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)

print("Saving locally...")
tokenizer.save_pretrained(SAVE_PATH)
model.save_pretrained(SAVE_PATH)

print("Done. Model saved to:", SAVE_PATH)
