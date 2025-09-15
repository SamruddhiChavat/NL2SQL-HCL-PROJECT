#make .env file to add gemini api (GEMINI_API_KEY=AIza...)

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiSQL:
    MODEL = "gemini-1.5-flash"

    FEW_SHOT_EXAMPLES = [
        {
            "nl": "Show top 5 defects with highest repair cost",
            "sql": "SELECT defect_id, repair_cost FROM defects ORDER BY repair_cost DESC LIMIT 5;"
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

    
    PROMPT_PREFIX = """You are a SQL generator.
Use the EXACT column names from the schema.
Produce ONLY one valid SQL SELECT statement. Do not add explanations.

Date handling rules:
- If user gives dates in natural language (e.g., '1 January 2024 to 3 March 2024'),
  convert them into 'YYYY-MM-DD' format in the SQL query.
- If user already gives dates in 'YYYY-MM-DD' format, keep them as is.
"""


    def __init__(self, model=MODEL):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(model)

    def build_prompt(self, schema_text, user_question):
        examples = "\n\n".join(
            [f"NL: \"{ex['nl']}\"\nSQL: {ex['sql']}" for ex in self.FEW_SHOT_EXAMPLES]
        )
        return f"""{self.PROMPT_PREFIX}

Schema:
{schema_text}

Examples:
{examples}

NL: "{user_question}"
SQL:"""

    def clean_sql(self, sql_text: str) -> str:
        sql = sql_text.strip()
        if sql.startswith("```"):
            sql = sql.strip("`")
            if sql.lower().startswith("sql"):
                sql = sql[3:].strip()
        if not sql.lower().startswith("select"):
            raise ValueError(f"Non-SELECT SQL generated: {sql}")
        return sql

    def generate_sql(self, schema_text, user_question):
        prompt = self.build_prompt(schema_text, user_question)
        response = self.model.generate_content(prompt)
        return self.clean_sql(response.text)
