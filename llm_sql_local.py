# llm_sql_local.py

import re
from dotenv import load_dotenv
import ollama
from ollama._types import ResponseError

load_dotenv()

MODEL_FALLBACK_LIST = [
    "mistral",
    "llama3:instruct",
    "phi",
]

FEW_SHOT_EXAMPLES = [
    {
        "nl": "Which customers placed the highest number of orders?",
        "sql": """SELECT o.customer_id, COUNT(o.order_id) AS total_orders
FROM orders o
GROUP BY o.customer_id
ORDER BY total_orders DESC;"""
    },
    {
        "nl": "Monthly sales for 2017 (sales come from order_items.price)",
        "sql": """SELECT
    YEAR(oi.shipping_limit_date) AS year,
    MONTH(oi.shipping_limit_date) AS month,
    SUM(oi.price) AS total_sales
FROM order_items oi
WHERE YEAR(oi.shipping_limit_date) = 2017
GROUP BY YEAR(oi.shipping_limit_date), MONTH(oi.shipping_limit_date)
ORDER BY year, month;"""
    },
    {
        "nl": "Show sellers and the total number of distinct products they sell",
        "sql": """SELECT
    oi.seller_id,
    COUNT(DISTINCT oi.product_id) AS total_products
FROM order_items oi
GROUP BY oi.seller_id
ORDER BY total_products DESC;"""
    },
    {
        "nl": "Orders where freight_value is above average and payment is by credit_card",
        "sql": """SELECT
    o.order_id,
    o.customer_id,
    pct.product_category_name_english
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN product_category_name_translation pct
    ON p.product_category_name = pct.product_category_name
WHERE oi.freight_value > (SELECT AVG(freight_value) FROM order_items)
  AND EXISTS (
      SELECT 1 FROM order_payments op
      WHERE op.order_id = o.order_id
        AND op.payment_type = 'credit_card'
  );"""
    },
]

PROMPT_PREFIX_MSSQL = """You are a SQL generator for Microsoft SQL Server (T-SQL).

RULES:
- Return exactly ONE valid SQL SELECT statement and nothing else.
- Use only the tables/columns listed in the Schema below.
- Use T-SQL date functions (YEAR, MONTH, DATEPART, FORMAT) where needed.
- Prefer fully-qualified columns (table.column) when there is any ambiguity.
- Use JOINs based on foreign keys when multiple tables are required.
- Never modify or create tables; only read data.
"""

PROMPT_PREFIX_SQLITE = """You are a SQL generator for SQLite.

RULES:
- Return exactly ONE valid SQL SELECT statement and nothing else.
- Use only the tables/columns listed in the Schema below.
- Use SQLite date functions (STRFTIME) where needed.
- Prefer fully-qualified columns (table.column) when there is any ambiguity.
- Use JOINs based on foreign keys when multiple tables are required.
- Never modify or create tables; only read data.
"""


class LocalLLM:
    def __init__(self, model: str = None, db_type: str = "sqlite"):
        self.model_list = MODEL_FALLBACK_LIST if model is None else [model]
        self.model = self.model_list[0]
        self.db_type = (db_type or "sqlite").lower()

        # Full schema text + parsed structures
        self.schema_text = None          # full text for debug
        self.schema_info = {}            # table -> [col1, col2, ...]
        self.col_to_tables = {}          # col.lower() -> set(table)
        self.foreign_keys = []           # not used now

    # ---------------------------
    #   SCHEMA / RAG LOGIC
    # ---------------------------

    def set_schema(self, schema_text: str):
        """
        Store full schema text and parse into table -> columns.
        Expects blocks like:
        Table: orders
        - order_id (TEXT)
        - customer_id (TEXT)
        """
        self.schema_text = schema_text
        self.schema_info = {}

        table = None
        for line in schema_text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"Table:\s*(\S+)", line)
            if m:
                table = m.group(1)
                self.schema_info[table] = []
                continue
            m2 = re.match(r"[-*]\s*([a-zA-Z0-9_]+)", line)
            if m2 and table:
                col = m2.group(1)
                self.schema_info[table].append(col)

        # reverse index
        self.col_to_tables = {}
        for t, cols in self.schema_info.items():
            for c in cols:
                self.col_to_tables.setdefault(c.lower(), set()).add(t)

    def _build_per_table_block(self, table: str) -> str:
        cols = self.schema_info.get(table, [])
        lines = [f"Table: {table}"]
        for c in cols:
            lines.append(f"- {c}")
        return "\n".join(lines)

    def get_relevant_schema(self, user_question: str, top_k: int = 5) -> str:
        """
        Simple RAG: choose top_k tables whose (table name + column names)
        overlap the most with words from the user question.
        """
        if not self.schema_info:
            return self.schema_text or ""

        uq_tokens = set(re.findall(r"[a-zA-Z_]+", user_question.lower()))
        if not uq_tokens:
            return self.schema_text or ""

        scored = []
        for table, cols in self.schema_info.items():
            tokens = set([table.lower()] + [c.lower() for c in cols])
            score = len(tokens & uq_tokens)
            scored.append((score, table))

        scored.sort(reverse=True, key=lambda x: x[0])

        non_zero = [t for s, t in scored if s > 0]
        if non_zero:
            chosen = non_zero[:top_k]
        else:
            chosen = [t for _, t in scored[:top_k]]

        blocks = [self._build_per_table_block(t) for t in chosen]
        return "\n\n".join(blocks)

    # ---------------------------
    #   PROMPT + SQL CLEANUP
    # ---------------------------

    def build_prompt(self, user_question: str, examples=None) -> str:
        if self.schema_text is None:
            raise RuntimeError("Schema not set. Call set_schema(schema_text) first.")

        if examples is None:
            examples = FEW_SHOT_EXAMPLES

        examples_text = "\n\n".join(
            [f'NL: "{ex["nl"]}"\nSQL: {ex["sql"]}' for ex in examples]
        )

        # RAG: only pass relevant schema subset, not full dump
        relevant_schema = self.get_relevant_schema(user_question, top_k=5)

        prefix = PROMPT_PREFIX_MSSQL if self.db_type == "mssql" else PROMPT_PREFIX_SQLITE

        return f"""{prefix}

Schema (only the most relevant tables/columns):
{relevant_schema}

Examples:
{examples_text}

NL: "{user_question}"
SQL:
"""

    def clean_sql(self, sql_text: str) -> str:
        text = sql_text.strip()
        if text.startswith("```"):
            text = text.strip("`")
        text = re.sub(r'^\s*sql\s*:\s*', '', text, flags=re.IGNORECASE)

        m = re.search(r"(SELECT\b.*?;)", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            sql = m.group(1).strip()
        else:
            sql = text

        if not sql.strip().endswith(";"):
            sql = sql.strip() + ";"

        if not sql.strip().lower().startswith("select"):
            raise ValueError("Model output does not contain a SELECT statement.")

        return sql

    def _engine_fixes(self, sql: str) -> str:
        s = sql

        # Generic YEAR() fix if model used EXTRACT()
        s = re.sub(
            r"EXTRACT\s*\(\s*YEAR\s+FROM\s+([a-zA-Z0-9_.]+)\s*\)",
            r"YEAR(\1)",
            s,
            flags=re.I,
        )

        if self.db_type == "sqlite":
            # SQLite: date functions
            s = re.sub(
                r"DATEPART\s*\(\s*year\s*,\s*([a-zA-Z0-9_.]+)\s*\)",
                r"STRFTIME('%Y', \1)",
                s,
                flags=re.I,
            )
            s = re.sub(
                r"DATEPART\s*\(\s*month\s*,\s*([a-zA-Z0-9_.]+)\s*\)",
                r"STRFTIME('%m', \1)",
                s,
                flags=re.I,
            )
            s = re.sub(
                r"DATEPART\s*\(\s*day\s*,\s*([a-zA-Z0-9_.]+)\s*\)",
                r"STRFTIME('%d', \1)",
                s,
                flags=re.I,
            )
        else:
            # MSSQL: convert any STRFTIME to YEAR/MONTH
            s = re.sub(
                r"STRFTIME\s*\(\s*'(%Y)'\s*,\s*([a-zA-Z0-9_.]+)\s*\)",
                r"YEAR(\2)",
                s,
                flags=re.I,
            )
            s = re.sub(
                r"STRFTIME\s*\(\s*'(%m)'\s*,\s*([a-zA-Z0-9_.]+)\s*\)",
                r"MONTH(\2)",
                s,
                flags=re.I,
            )

            # Fix invalid "SELECT TOP n DISTINCT" → "SELECT DISTINCT TOP n"
            s = re.sub(
                r"(?i)SELECT\s+TOP\s+(\d+)\s+DISTINCT",
                r"SELECT DISTINCT TOP \1",
                s,
            )

            # Strip trailing LIMIT for SQL Server (we rely on TOP)
            s = re.sub(
                r"(?i)\s+LIMIT\s+\d+\s*;?\s*$",
                ";",
                s,
            )

            # Fix common city/state mistakes on customers
            s = re.sub(r"\bc\.city\b", "c.customer_city", s)
            s = re.sub(r"\bc\.state\b", "c.customer_state", s)
            s = re.sub(r"\bcustomers\.city\b", "customers.customer_city", s, flags=re.I)
            s = re.sub(r"\bcustomers\.state\b", "customers.customer_state", s, flags=re.I)

            # Disambiguate product_id when joining order_items + products
            if re.search(r"\bFROM\s+order_items\b", s, re.I) and re.search(r"\bJOIN\s+products\b", s, re.I):
                s = re.sub(
                    r"(?<!\.)\bproduct_id\b",
                    "products.product_id",
                    s,
                )

        return s

    def _auto_prefix_columns(self, sql: str) -> str:
        s = sql
        tokens = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", sql))
        keywords = {
            "select", "from", "where", "join", "on", "group", "by", "order",
            "as", "limit", "and", "or", "sum", "avg", "count", "min", "max",
            "having", "in", "is", "null", "exists", "case", "when", "then", "else",
            "top", "offset", "fetch", "into", "distinct", "left", "right",
            "inner", "outer", "full", "year", "month", "day",
        }

        candidates = [t for t in tokens if t.lower() not in keywords and not t.isdigit()]
        candidates.sort(key=len, reverse=True)

        for cand in candidates:
            lower = cand.lower()
            tables = self.col_to_tables.get(lower, set())
            if len(tables) == 1:
                table = list(tables)[0]
                s = re.sub(
                    rf"(?<![\.\w])\b{re.escape(cand)}\b",
                    f"{table}.{cand}",
                    s,
                )
        return s

    def validate_sql_columns(self, sql: str):
        sql_no_strings = re.sub(r"'[^']*'", "", sql.lower())

        alias_map = {}
        for m in re.finditer(
            r'\b(?:from|join)\s+([a-zA-Z0-9_]+)(?:\s+(?:as\s+)?([a-zA-Z0-9_]+))?',
            sql_no_strings,
            flags=re.I,
        ):
            table = m.group(1)
            alias = m.group(2)
            if alias:
                alias_map[alias.lower()] = table.lower()

        tokens = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_\.]*)\b", sql_no_strings))

        invalid = []
        keywords = {
            "select", "from", "where", "join", "on", "group", "by", "order",
            "as", "limit", "and", "or", "sum", "avg", "count", "min", "max",
            "having", "in", "is", "null", "exists", "case", "when", "then", "else",
            "top", "offset", "fetch", "into", "distinct", "left", "right", "inner",
            "outer", "full", "year", "month", "day",
            "strftime", "datepart", "extract", "convert", "cast", "format",
            "substr", "like", "datetime", "between", "asc", "desc",
        }

        table_names = {t.lower() for t in self.schema_info.keys()}

        for tok in tokens:
            if tok in keywords or tok.isdigit():
                continue

            if tok in table_names:
                continue

            if "." in tok:
                left, col = tok.split(".", 1)
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
            sample = invalid[:12]
            raise ValueError(
                f"LLM generated invalid column(s) or tokens: {sample}"
                + ("..." if len(invalid) > 12 else "")
            )

        return True

    def _apply_limit_style(self, sql: str, limit: int):
        if limit is None:
            return sql
        if self.db_type == "sqlite":
            if re.search(r"\blimit\b", sql, flags=re.I):
                return sql
            return sql.rstrip().rstrip(";") + f" LIMIT {limit};"
        else:
            # MSSQL: add TOP N after SELECT if not present
            if re.search(r"\bTOP\s+\d+\b", sql, flags=re.I) or re.search(r"\bOFFSET\b", sql, flags=re.I):
                return sql
            return re.sub(
                r"^\s*SELECT\s",
                f"SELECT TOP {limit} ",
                sql,
                flags=re.I,
            )

    def generate_sql(self, schema_text: str, user_question: str, examples=None, result_limit: int = 200) -> str:
        if self.schema_text != schema_text:
            self.set_schema(schema_text)

        prompt = self.build_prompt(user_question, examples)
        last_raw = ""

        for model_name in self.model_list:
            try:
                print(f"Trying model: {model_name}")
                response = ollama.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_sql = response["message"]["content"].strip()
                print("RAW MODEL OUTPUT:\n", raw_sql)
                last_raw = raw_sql

                sql = self.clean_sql(raw_sql)
                sql = self._engine_fixes(sql)
                sql = self._auto_prefix_columns(sql)
                sql_with_limit = self._apply_limit_style(sql, result_limit)

                # Try validation, but don't block the whole flow if it fails
                try:
                    self.validate_sql_columns(sql_with_limit)
                except ValueError as ve:
                    print("WARNING (schema validation):", ve)

                return sql_with_limit

            except ResponseError as e:
                if "requires more system memory" in str(e).lower():
                    print(f"Model '{model_name}' failed due to memory. Trying next fallback...")
                    continue
                else:
                    raise

        raise RuntimeError("All fallback models failed.")
