import re
import os
import torch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

load_dotenv()

# ---------------------------
#   PROMPT PREFIXES
# ---------------------------

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
"""

# ---------------------------
#   LOCAL LLM CLASS
# ---------------------------

class LocalLLM:
    def __init__(self, db_type="mssql"):
        self.db_type = db_type.lower()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MODEL_DIR = os.path.join(BASE_DIR, "models")
        BASE_MODEL_PATH = os.path.join(MODEL_DIR, "flan-t5-base")
        LORA_PATH = os.path.join(MODEL_DIR, "nl2sql-lora-trained")

        if not os.path.exists(os.path.join(LORA_PATH, "adapter_config.json")):
            raise FileNotFoundError(f"adapter_config.json not found in {LORA_PATH}")
        if not os.path.exists(BASE_MODEL_PATH):
            raise FileNotFoundError(f"Base model not found at {BASE_MODEL_PATH}")

        self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, local_files_only=True)

        base_model = AutoModelForSeq2SeqLM.from_pretrained(
            BASE_MODEL_PATH,
            local_files_only=True,
            torch_dtype=torch.float32
        )

        self.model = PeftModel.from_pretrained(
            base_model,
            LORA_PATH,
            local_files_only=True
        )

        self.model.eval()

    # ---------------------------
    #   SCHEMA / RAG LOGIC
    # ---------------------------

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
        scored = []
        for table, cols in self.schema_info.items():
            tokens = set([table.lower()] + [c.lower() for c in cols])
            scored.append((len(tokens & uq_tokens), table))
        scored.sort(reverse=True)
        chosen = [t for s, t in scored if s > 0][:top_k] or [t for _, t in scored[:top_k]]
        return "\n\n".join(self._build_per_table_block(t) for t in chosen)

    # ---------------------------
    #   PROMPT + SQL CLEANUP
    # ---------------------------

    def build_prompt(self, user_question: str) -> str:
        if self.schema_text is None:
            raise RuntimeError("Schema not set.")
        prefix = PROMPT_PREFIX_MSSQL if self.db_type == "mssql" else PROMPT_PREFIX_SQLITE
        relevant_schema = self.get_relevant_schema(user_question)
        return f"""{prefix}

Schema:
{relevant_schema}

NL: "{user_question}"
SQL:
"""

    def clean_sql(self, sql_text: str) -> str:
        text = sql_text.strip().strip("`")
        m = re.search(r"(SELECT\b.*?;)", text, re.I | re.S)
        sql = m.group(1).strip() if m else text
        if not sql.lower().startswith("select"):
            raise ValueError("No SELECT found.")
        return sql if sql.endswith(";") else sql + ";"

    # ---------------------------
    #   ENGINE FIXES + SAFETY
    # ---------------------------

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
        keywords = {"select","from","where","join","on","group","by","order","as","and","or","sum","avg","count","distinct","year","month"}
        for tok in sorted(tokens, key=len, reverse=True):
            if tok.lower() in keywords:
                continue
            tables = self.col_to_tables.get(tok.lower())
            if tables and len(tables) == 1:
                sql = re.sub(rf"\b{tok}\b", f"{list(tables)[0]}.{tok}", sql)
        return sql

    def _apply_limit_style(self, sql: str, limit: int):
        if self.db_type == "sqlite":
            return sql if "limit" in sql.lower() else sql[:-1] + f" LIMIT {limit};"
        return sql if "top" in sql.lower() else re.sub(r"SELECT", f"SELECT TOP {limit}", sql, 1, flags=re.I)

    # ---------------------------
    #   MAIN GENERATION
    # ---------------------------

    def generate_sql(self, schema_text: str, user_question: str, result_limit: int = 200) -> str:
        if self.schema_text != schema_text:
            self.set_schema(schema_text)

        prompt = self.build_prompt(user_question)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False
            )

        raw_sql = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        print("RAW MODEL OUTPUT:\n", raw_sql)

        sql = self.clean_sql(raw_sql)
        sql = self._engine_fixes(sql)
        sql = self._auto_prefix_columns(sql)
        sql = self._apply_limit_style(sql, result_limit)

        return sql
