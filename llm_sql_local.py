import os
import re
import torch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

load_dotenv()


PROMPT_PREFIX_MSSQL = """You are a SQL generator for Microsoft SQL Server (T-SQL).

RULES:
- Return exactly ONE valid SQL SELECT statement and nothing else.
- Use only the tables/columns listed in the Schema below.
- Use T-SQL date functions (YEAR, MONTH, DATEPART, FORMAT) where needed.
- Prefer fully-qualified columns (table.column) when there is any ambiguity.
- Use JOINs based on foreign keys when multiple tables are required.
- Never modify or create tables; only read data.
- Never add any explanation or extra text.
"""

PROMPT_PREFIX_SQLITE = """You are a SQL generator for SQLite.

RULES:
- Return exactly ONE valid SQL SELECT statement and nothing else.
- Use only the tables/columns listed in the Schema below.
- Use SQLite date functions (STRFTIME) where needed.
- Prefer fully-qualified columns (table.column) when there is any ambiguity.
- Use JOINs based on foreign keys when multiple tables are required.
- Never modify or create tables; only read data.
- Never add any explanation or extra text.
"""

FEW_SHOT_EXAMPLES = [
    {
        "nl": "Which customers placed the highest number of orders?",
        "sql": (
            "SELECT o.customer_id, COUNT(o.order_id) AS total_orders "
            "FROM orders o "
            "GROUP BY o.customer_id "
            "ORDER BY total_orders DESC;"
        ),
    },
    {
        "nl": "Monthly sales for 2017 (sales come from order_items.price)",
        "sql": (
            "SELECT DATEPART(year, oi.shipping_limit_date) AS year, "
            "DATEPART(month, oi.shipping_limit_date) AS month, "
            "SUM(oi.price) AS total_sales "
            "FROM order_items oi "
            "WHERE DATEPART(year, oi.shipping_limit_date) = 2017 "
            "GROUP BY DATEPART(year, oi.shipping_limit_date), "
            "DATEPART(month, oi.shipping_limit_date) "
            "ORDER BY year, month;"
        ),
    },
    {
        "nl": "Show sellers and the total number of distinct products they sell",
        "sql": (
            "SELECT oi.seller_id, COUNT(DISTINCT oi.product_id) AS total_products "
            "FROM order_items oi "
            "GROUP BY oi.seller_id "
            "ORDER BY total_products DESC;"
        ),
    },
    {
        "nl": "Orders where freight_value is above average and payment is by credit_card",
        "sql": (
            "SELECT o.order_id, o.customer_id, pct.product_category_name_english "
            "FROM order_items oi "
            "JOIN orders o ON oi.order_id = o.order_id "
            "JOIN products p ON oi.product_id = p.product_id "
            "LEFT JOIN product_category_name_translation pct "
            "ON p.product_category_name = pct.product_category_name "
            "WHERE oi.freight_value > (SELECT AVG(freight_value) FROM order_items) "
            "AND EXISTS (SELECT 1 FROM order_payments op "
            "WHERE op.order_id = o.order_id AND op.payment_type = 'credit_card');"
        ),
    },
    {
        "nl": "Show the top 20 sellers by number of orders",
        "sql": (
            "SELECT TOP 20 oi.seller_id, COUNT(DISTINCT oi.order_id) AS total_orders "
            "FROM order_items oi "
            "GROUP BY oi.seller_id "
            "ORDER BY total_orders DESC;"
        ),
    },
]


class LocalLLM:
    def __init__(self, db_type: str = "mssql"):
        self.db_type = db_type.lower()
        self.device = "cpu"

        base_dir = os.path.dirname(os.path.abspath(__file__))

        base_model_path = os.path.join(base_dir, "model", "models", "flan_t5_base")
        lora_path = os.path.join(base_dir, "nl2sql-lora-trained")

        if not os.path.exists(os.path.join(lora_path, "adapter_config.json")):
            raise FileNotFoundError(f"adapter_config.json not found in {lora_path}")
        if not os.path.exists(base_model_path):
            raise FileNotFoundError(f"Base model not found at {base_model_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            base_model_path,
            local_files_only=True
        )

        base_model = AutoModelForSeq2SeqLM.from_pretrained(
            base_model_path,
            local_files_only=True,
            torch_dtype=torch.float32
        )

        self.model = PeftModel.from_pretrained(
            base_model,
            lora_path,
            local_files_only=True
        )
        self.model.eval()

        self.schema_text: str | None = None
        self.schema_info: dict[str, list[str]] = {}
        self.col_to_tables: dict[str, set[str]] = {}

    def set_schema(self, schema_text: str):
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
                self.schema_info[table].append(m2.group(1))

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
        if not self.schema_info:
            return self.schema_text or ""
        uq_tokens = set(re.findall(r"[a-zA-Z_]+", user_question.lower()))
        scored: list[tuple[int, str]] = []
        for table, cols in self.schema_info.items():
            tokens = set([table.lower()] + [c.lower() for c in cols])
            scored.append((len(tokens & uq_tokens), table))
        scored.sort(reverse=True)
        chosen = [t for s, t in scored if s > 0][:top_k] or [t for _, t in scored[:top_k]]
        return "\n\n".join(self._build_per_table_block(t) for t in chosen)

    def build_prompt(self, user_question: str) -> str:
        if self.schema_text is None:
            raise RuntimeError("Schema not set.")
        prefix = PROMPT_PREFIX_MSSQL if self.db_type == "mssql" else PROMPT_PREFIX_SQLITE
        relevant_schema = self.get_relevant_schema(user_question)
        examples_text = "\n\n".join(
            [f'NL: "{ex["nl"]}"\nSQL: {ex["sql"]}' for ex in FEW_SHOT_EXAMPLES]
        )
        return f"""{prefix}

Schema:
{relevant_schema}

Examples:
{examples_text}

NL: "{user_question}"
SQL:
"""

    def clean_sql(self, sql_text: str) -> str:
        text = sql_text.strip().strip("`")
        if text.lower() in {"undefined", "null", "none", ""}:
            raise ValueError("Model returned no valid SQL text.")
        m = re.search(r"(SELECT\b.*?;)", text, re.I | re.S)
        sql = m.group(1).strip() if m else text
        if not sql.lower().startswith("select"):
            raise ValueError("No SELECT found in model output.")
        if not sql.endswith(";"):
            sql += ";"
        return sql

    def _engine_fixes(self, sql: str) -> str:
        s = re.sub(r"EXTRACT\s*\(\s*YEAR\s+FROM\s*([^)]+)\)", r"YEAR(\1)", sql, flags=re.I)
        if self.db_type == "mssql":
            s = re.sub(r"STRFTIME\s*\(\s*'%Y'\s*,\s*([^)]+)\)", r"YEAR(\1)", s, flags=re.I)
            s = re.sub(r"STRFTIME\s*\(\s*'%m'\s*,\s*([^)]+)\)", r"MONTH(\1)", s, flags=re.I)
            s = re.sub(r"\s+LIMIT\s+\d+\s*;?$", ";", s, flags=re.I)
            s = re.sub(r"(?i)SELECT\s+TOP\s+(\d+)\s+DISTINCT", r"SELECT DISTINCT TOP \1", s)
        return s

    def _auto_prefix_columns(self, sql: str) -> str:
        tokens = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", sql))
        keywords = {
            "select", "from", "where", "join", "on", "group", "by", "order", "as",
            "and", "or", "sum", "avg", "count", "distinct", "year", "month",
            "top", "limit", "inner", "left", "right", "outer"
        }
        for tok in sorted(tokens, key=len, reverse=True):
            if tok.lower() in keywords:
                continue
            tables = self.col_to_tables.get(tok.lower())
            if tables and len(tables) == 1:
                table = list(tables)[0]
                sql = re.sub(rf"\b{tok}\b", f"{table}.{tok}", sql)
        return sql

    def _apply_limit_style(self, sql: str, limit: int) -> str:
        if limit is None:
            return sql
        if self.db_type == "sqlite":
            if "limit" in sql.lower():
                return sql
            return sql.rstrip().rstrip(";") + f" LIMIT {limit};"
        if " top " in sql.lower():
            return sql
        return re.sub(r"SELECT", f"SELECT TOP {limit}", sql, 1, flags=re.I)

    def generate_sql(self, schema_text: str, user_question: str,
                     result_limit: int = 200) -> str:
        if self.schema_text != schema_text:
            self.set_schema(schema_text)

        prompt = self.build_prompt(user_question)

        print("\n[MODEL] Starting generation...")
        print(f"[MODEL] Question: {user_question}")

        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=1024
            )

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    num_beams=4,
                )

            raw_sql = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            print("[MODEL] Raw output:")
            print(raw_sql)

            sql = self.clean_sql(raw_sql)
            sql = self._engine_fixes(sql)
            sql = self._auto_prefix_columns(sql)
            sql = self._apply_limit_style(sql, result_limit)

            print("[MODEL] Finished successfully.\n")
            return sql

        except Exception as e:
            print(f"[MODEL] FAILED with error: {e}\n")
            raise
