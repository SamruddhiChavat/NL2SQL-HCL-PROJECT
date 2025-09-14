# llm_sql_local.py

import os
import ollama
from dotenv import load_dotenv
from ollama._types import ResponseError  # For catching memory errors

# Load environment variables
load_dotenv()

# Model fallback preference order (first = preferred, last = lightest)
MODEL_FALLBACK_LIST = [
    "phi",
    "mistral",
    "llama3:3b"
]

# Few-shot examples
FEW_SHOT_EXAMPLES = [
    {
        "nl": "Show top 5 defects with highest repair cost",
        "sql": "SELECT * FROM defects ORDER BY repair_cost DESC LIMIT 5;"
    },
    {
        "nl": "Count defects by defect_type for product 12345",
        "sql": "SELECT defect_type, COUNT(*) AS cnt FROM defects WHERE product_id = '12345' GROUP BY defect_type;"
    },
    {
        "nl": "Average repair_cost for defects in Assembly A between 2024-01-01 and 2024-03-31",
        "sql": "SELECT AVG(repair_cost) AS avg_cost FROM defects WHERE defect_location = 'Assembly A' AND defect_date BETWEEN '2024-01-01' AND '2024-03-31';"
    },
    {
    "nl": "Show defects from last 7 days",
    "sql": "SELECT * FROM defects WHERE defect_date >= date('now', '-7 day');"
},

]
PROMPT_PREFIX = """You are a SQL generator for SQLite. Use the EXACT column names from the schema. 
Produce ONLY one valid SQL SELECT statement. Do not add explanations. 
Dates must be in 'YYYY-MM-DD' format.
Use SQLite date functions like date('now', '-N day') for relative dates."""


class LocalLLM:
    def __init__(self, model: str = None):
        self.model_list = MODEL_FALLBACK_LIST if model is None else [model]
        self.model = self.model_list[0]  # start with first

    def build_prompt(self, schema_text: str, user_question: str, examples=None) -> str:
        if examples is None:
            examples = FEW_SHOT_EXAMPLES

        examples_text = "\n\n".join([f"NL: \"{ex['nl']}\"\nSQL: {ex['sql']}" for ex in examples])

        return f"""{PROMPT_PREFIX}

Schema:
{schema_text}

Examples:
{examples_text}

NL: "{user_question}"
SQL:"""

    def generate_sql(self, schema_text: str, user_question: str, examples=None) -> str:
        prompt = self.build_prompt(schema_text, user_question, examples)

        # Try models one by one
        for model_name in self.model_list:
            try:
                print(f"🔍 Trying model: {model_name}")
                response = ollama.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}]
                )
                self.model = model_name  # Update to the working model
                return response["message"]["content"].strip()

            except ResponseError as e:
                if "requires more system memory" in str(e):
                    print(f"Model '{model_name}' failed due to memory. Trying next...")
                    continue  # Try next fallback model
                else:
                    raise  # Unknown error — don't hide it

        raise RuntimeError("All fallback models failed due to insufficient memory or other errors.")
