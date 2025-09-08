#make .env file to add gemini api (GEMINI_API_KEY=AIza...)
import os
import google.generativeai as genai

from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-1.5-flash"   # You can change to "gemini-1.5-pro" for more complex tasks

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
]

PROMPT_PREFIX = """You are a SQL generator. Use the EXACT column names from the schema. 
Produce ONLY one valid SQL SELECT statement. Do not add explanations. 
Dates must be in 'YYYY-MM-DD' format."""

def build_prompt(schema_text, user_question):
    examples = "\n\n".join([f"NL: \"{ex['nl']}\"\nSQL: {ex['sql']}" for ex in FEW_SHOT_EXAMPLES])
    prompt = f"""{PROMPT_PREFIX}

Schema:
{schema_text}

Examples:
{examples}

NL: "{user_question}"
SQL:"""
    return prompt

def generate_sql_with_gemini(schema_text, user_question, model=MODEL):
    prompt = build_prompt(schema_text, user_question)
    
    response = genai.GenerativeModel(model).generate_content(prompt)
    
    sql = response.text.strip()
    return sql
