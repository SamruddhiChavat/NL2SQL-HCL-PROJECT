import os
import re
from dotenv import load_dotenv
import ollama
from ollama._types import ResponseError

load_dotenv()

MODEL_FALLBACK_LIST = [
    "mistral",
    "phi"
]

# few-shot examples 
FEW_SHOT_EXAMPLES = [
    {
        "nl": "Show top 5 customers with most orders",
        "sql": "SELECT TOP 5 customer_id, COUNT(order_id) AS total_orders FROM orders GROUP BY customer_id ORDER BY total_orders DESC;"
    },
    {
        "nl": "List product categories in English and Portuguese",
        "sql": "SELECT TOP 10 product_category_name, product_category_name_english FROM product_category_name_translation;"
    },
    {
        "nl": "Show average payment value by payment_type",
        "sql": "SELECT payment_type, AVG(payment_value) AS avg_payment FROM order_payments GROUP BY payment_type;"
    },
    {
        "nl": "Get last 5 reviews with comments",
        "sql": "SELECT TOP 5 review_comment_message, review_score FROM order_reviews ORDER BY review_id DESC;"
    },
    {
        "nl": "Show total sales per product category",
        "sql": """SELECT p.product_category_name, SUM(oi.price + oi.freight_value) AS total_sales
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
GROUP BY p.product_category_name
ORDER BY total_sales DESC;"""
    },
    {
        "nl": "List customers who spent more than 500 in total",
        "sql": """SELECT c.customer_id, SUM(oi.price + oi.freight_value) AS total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY c.customer_id
HAVING SUM(oi.price + oi.freight_value) > 500
ORDER BY total_spent DESC;"""
    }
]


PROMPT_PREFIX_MSSQL =  """You are a strict SQL generator for Microsoft SQL Server (T-SQL).

RULES:
1. Always respond with exactly ONE valid SQL SELECT statement, nothing else.
2. Use ONLY tables and columns listed in the schema below; do NOT invent anything.
3. Join tables using foreign keys if needed (e.g., customer_id, order_id, product_id, seller_id).
4. Date format must be 'YYYY-MM-DD'. Use SQL Server functions like DATEPART, FORMAT, GETDATE() as needed.
5. Use TOP N instead of LIMIT for row restrictions.
6. If a column does not exist in the schema, do NOT attempt to use it.
7. If the query cannot be generated from the available schema, return:
   SELECT 'Error: Query cannot be generated from available schema';
"""


class LocalLLM:
    def __init__(self, model: str = None, db_type: str = "mssql"):
        self.model_list = MODEL_FALLBACK_LIST if model is None else [model]
        self.model = self.model_list[0]
        self.db_type = (db_type or "mssql").lower()
        self.schema_text = None
        self.schema_info = {}
        self.col_to_tables = {}
        self.foreign_keys = []

    def set_schema(self, schema_text: str):
        self.schema_text = schema_text
        table = None
        self.schema_info = {}
        for line in schema_text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"Table:\s*(\S+)", line)
            if m:
                table = m.group(1).lower()
                self.schema_info[table] = []
                continue
            m2 = re.match(r"[-*]\s*([a-zA-Z0-9_]+)", line)
            if m2 and table:
                col = m2.group(1).lower()
                self.schema_info[table].append(col)
        self.col_to_tables = {}
        for t, cols in self.schema_info.items():
            for c in cols:
                self.col_to_tables.setdefault(c.lower(), set()).add(t)

    def build_prompt(self, user_question: str, examples=None) -> str:
        if self.schema_text is None:
            raise RuntimeError("Schema not set. Call set_schema(schema_text) first.")
        if examples is None:
            examples = FEW_SHOT_EXAMPLES
        examples_text = "\n\n".join([f"NL: \"{ex['nl']}\"\nSQL: {ex['sql']}" for ex in examples])
        prefix = PROMPT_PREFIX_MSSQL
        return f"""{prefix}

Schema:
{self.schema_text}

Examples:
{examples_text}

NL: "{user_question}"
SQL:
"""

    def clean_sql(self, sql_text: str) -> str:
        text = sql_text.strip()
        
        if text.startswith("```"):
            text = text.strip("`")
        # removes leading "sql:" or similar
        text = re.sub(r'^\s*sql\s*:\s*', '', text, flags=re.IGNORECASE)
        # extracts first SELECT ... ; block
        m = re.search(r"(SELECT\b[\s\S]*?;)", text, flags=re.IGNORECASE)
        if m:
            sql = m.group(1).strip()
        else:
            # fallback: 
            m2 = re.search(r"(SELECT\b[\s\S]*)", text, flags=re.IGNORECASE)
            if m2:
                sql = m2.group(1).strip()
                if not sql.endswith(";"):
                    sql = sql + ";"
            else:
                raise ValueError("Model output does not contain a SELECT statement.")
        if not sql.strip().lower().startswith("select"):
            raise ValueError("Model output does not contain a SELECT statement.")
        return sql

    def _engine_fixes(self, sql: str) -> str:
        s = sql
        # common conversions 
        s = re.sub(r"EXTRACT\s*\(\s*YEAR\s+FROM\s+([a-zA-Z0-9_.]+)\s*\)", r"DATEPART(year, \1)", s, flags=re.I)
        
        s = re.sub(r"STRFTIME\s*\(\s*'%Y'\s*,\s*([a-zA-Z0-9_.]+)\s*\)", r"DATEPART(year, \1)", s, flags=re.I)
        s = re.sub(r"STRFTIME\s*\(\s*'%m'\s*,\s*([a-zA-Z0-9_.]+)\s*\)", r"DATEPART(month, \1)", s, flags=re.I)
        s = re.sub(r"STRFTIME\s*\(\s*'%d'\s*,\s*([a-zA-Z0-9_.]+)\s*\)", r"DATEPART(day, \1)", s, flags=re.I)
        # MSSQL: converts SQLite || concatenation into +
        s = re.sub(r"\s*\|\|\s*", " + ", s)
        return s

    def _auto_prefix_columns(self, sql: str) -> str:
        
        s = sql
        # to ensure no prefix tokens that are already dotted references or are keywords or short
        tokens = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", sql))
        keywords = {"select","from","where","join","on","group","by","order","as","limit","and","or",
                    "sum","avg","count","min","max","having","in","is","null","exists","case","when","then","else","top","offset","fetch"}
        candidates = [t for t in tokens if t.lower() not in keywords and not t.isdigit()]
        # sort by length descending to avoid partial matches
        candidates.sort(key=len, reverse=True)
        for cand in candidates:
            
            if "." in cand or len(cand) <= 2:
                continue
            lower = cand.lower()
            tables = self.col_to_tables.get(lower, set())
            if len(tables) == 1:
                table = list(tables)[0]
                # only replace whole-word occurrences 
                s = re.sub(rf"(?<![\.\w])\b{re.escape(cand)}\b", f"{table}.{cand}", s)
        return s

    def validate_sql_columns(self, sql: str):
        # this will print helpful warnings for debugging; returns True if invalid tokens found
        sql_no_strings = re.sub(r"'[^']*'", "", sql.lower())
        alias_map = {}
        for m in re.finditer(r'\b(?:from|join)\s+([a-zA-Z0-9_]+)(?:\s+(?:as\s+)?([a-zA-Z0-9_]+))?', sql_no_strings, flags=re.I):
            table = m.group(1)
            alias = m.group(2)
            if alias:
                alias_map[alias.lower()] = table.lower()
        tokens = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_\.]*)\b", sql_no_strings))
        invalid = []
        keywords = {
            "select","from","where","join","on","group","by","order","as","limit","and","or",
            "sum","avg","count","min","max","having","in","is","null","exists","case","when","then","else",
            "top","offset","fetch","into","distinct","left","right","inner","outer","full",
            "strftime","datepart","extract","convert","cast","format","substr","like","datetime","between",
            "asc","desc"
        }
        table_names = {t.lower() for t in self.schema_info.keys()}
        for tok in tokens:
            if tok in keywords or tok.isdigit():
                continue
            if tok in table_names:
                continue
            if '.' in tok:
                left, col = tok.split('.', 1)
                if left in alias_map:
                    real_table = alias_map[left]
                    cols = [c.lower() for c in self.schema_info.get(real_table, [])]
                    if col not in cols:
                        invalid.append(tok)
                    continue
                if left not in table_names:
                    invalid.append(tok)
                    continue
                cols = [c.lower() for c in self.schema_info.get(left, [])]
                if col not in cols:
                    invalid.append(tok)
                continue
            if tok in self.col_to_tables:
                continue
            if tok in alias_map:
                continue
            if len(tok) <= 2:
                continue
            invalid.append(tok)
        if invalid:
            print(f" WARNING: LLM generated invalid column(s) or tokens: {invalid}")
            return True
        return False

    def _apply_limit_style(self, sql: str, limit: int):
        if limit is None:
            return sql
        if self.db_type == "sqlite":
            if re.search(r"\blimit\b", sql, flags=re.I):
                return sql
            return sql.rstrip().rstrip(";") + f" LIMIT {limit};"
        else:
            if re.search(r"\bTOP\s+\d+\b", sql, flags=re.I) or re.search(r"\bOFFSET\b", sql, flags=re.I):
                return sql
            return re.sub(r"^\s*SELECT\s", f"SELECT TOP {limit} ", sql, flags=re.I)

    def generate_sql(self, schema_text: str, user_question: str, examples=None, result_limit: int = 200) -> str:
        if self.schema_text != schema_text:
            self.set_schema(schema_text)
        prompt = self.build_prompt(user_question, examples)
        last_raw = ""
        for model_name in self.model_list:
            try:
                print(f"Trying model: {model_name}")
                # provides a system role to bias the model to return SQL only and deterministic outputs
                messages = [
                    {"role": "system", "content": "You are a helpful assistant that MUST return exactly one T-SQL SELECT statement and nothing else. No explanation."},
                    {"role": "user", "content": prompt}
                ]
                # sets temperature = 0 for determinism;
                response = ollama.chat(model=model_name, messages=messages, options={"temperature": 0})
                raw_sql = response.get("message", {}).get("content", "").strip()
                print("RAW MODEL OUTPUT:\n", raw_sql)
                last_raw = raw_sql
                sql = self.clean_sql(raw_sql)
                sql = self._engine_fixes(sql)
                sql = self._auto_prefix_columns(sql)
                sql_with_limit = self._apply_limit_style(sql, result_limit)
                invalid = self.validate_sql_columns(sql_with_limit)
                # if invalid, still return but print warning
                return sql_with_limit
            except ResponseError as e:
                if "requires more system memory" in str(e).lower():
                    print(f"Model '{model_name}' failed due to memory. Trying next fallback... ({e})")
                    continue
                else:
                    raise
            except ValueError as ve:
                
                try:
                    attempt = self._engine_fixes(last_raw)
                    attempt = self._auto_prefix_columns(attempt)
                    attempt = self._apply_limit_style(attempt, result_limit)
                    self.validate_sql_columns(attempt)
                    return attempt
                except Exception:
                    raise ve
        raise RuntimeError("All fallback models failed.")
