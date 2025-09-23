# make .env file to add gemini api (GEMINI_API_KEY=AIza...)
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiSQL:
    MODEL = "gemini-1.5-flash"

    # Few-shot examples for multi-table schema
    FEW_SHOT_EXAMPLES = [
        {
            "nl": "Show top 5 defects with highest repair cost",
            "sql": "SELECT d.defect_id, d.repair_cost FROM defects d ORDER BY d.repair_cost DESC LIMIT 5;"
        },
        {
            "nl": "Count defects by defect_type for product 12345",
            "sql": "SELECT d.defect_type, COUNT(*) AS cnt FROM defects d JOIN products p ON d.product_id = p.product_id WHERE p.product_id = '12345' GROUP BY d.defect_type;"
        },
        {
            "nl": "Show all inspection methods used for defects",
            "sql": "SELECT DISTINCT im.inspection_method FROM inspection_methods im JOIN defects d ON d.method_id = im.method_id;"
        },
        {
            "nl": "Average repair_cost for defects in Assembly A between 2024-01-01 and 2024-03-31",
            "sql": "SELECT AVG(d.repair_cost) AS avg_cost FROM defects d JOIN inspection_methods im ON d.method_id = im.method_id WHERE im.defect_location = 'Assembly A' AND d.defect_date BETWEEN '2024-01-01' AND '2024-03-31';"
        }
    ]

    PROMPT_PREFIX = """You are an expert SQL generator for a SQLite database with multiple tables.

Follow these rules carefully:
- Use ONLY the exact column names and table names from the schema provided.
- If a column name appears in multiple tables, qualify it with table alias (e.g., d.defect_id).
- Always use explicit JOINs when fetching data across tables.
- Always return exactly ONE SQL SELECT query unless explicitly instructed otherwise.
- Do NOT invent columns or tables not present in the schema.
- Dates:
  - Convert natural language dates to 'YYYY-MM-DD'.
  - If the date is already in 'YYYY-MM-DD', leave it unchanged.
  - If the date is given in another format (e.g., 'DD-MM-YYYY'), reply with: NOTE: Please provide the date in 'YYYY-MM-DD' format.
- Output format:
  Always respond in the format:
  SQL:
  <single SQL SELECT statement>
  NOTE: <optional short English clarification if needed>

Think step by step:
1. Identify relevant tables and columns from schema.
2. Decide necessary JOINs and filters.
3. Write the final SQL query using correct syntax.
4. Optionally add a NOTE if clarification is needed.
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
Response:"""

    def clean_sql(self, sql_text: str) -> (str, str):
        """
        Returns tuple (sql, note)
        If response includes 'NOTE:' line, separate it into 'note'.
        """
        text = sql_text.strip()

        # removes markdown fences
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("sql"):
                text = text[3:].strip()

        # removes optional SQL: prefix
        if text.lower().startswith("sql:"):
            text = text[4:].strip()

        # separates NOTE
        note = ""
        lines = [l.strip() for l in text.splitlines() if l.strip() != ""]
        note_lines = [l for l in lines if l.upper().startswith("NOTE:")]
        if note_lines:
            idx = next(i for i, l in enumerate(lines) if l.upper().startswith("NOTE:"))
            sql_lines = lines[:idx]
            note = " ".join([l[len("NOTE:"):].strip() for l in lines[idx:]])
            sql = " ".join(sql_lines)
        else:
            joined = " ".join(lines)
            if ";" in joined:
                last_semi = joined.rfind(";")
                sql = joined[:last_semi+1].strip()
                remainder = joined[last_semi+1:].strip()
                note = remainder
            else:
                sql = joined
                note = ""

        sql = sql.strip()
        if not sql.lower().startswith("select"):
            raise ValueError(f"Non-SELECT SQL generated: {sql}")

        return sql, note

    def generate_sql(self, schema_text, user_question):
        prompt = self.build_prompt(schema_text, user_question)
        response = self.model.generate_content(prompt)
        sql, note = self.clean_sql(response.text)
        return sql, note
