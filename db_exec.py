# db_exec.py
import re
import sqlparse
import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = "defects.db"
TABLE = "defects"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

FORBIDDEN = re.compile(
    r'\b(insert|update|delete|drop|alter|create|truncate|attach|detach|grant|revoke|replace|merge)\b',
    re.I
)

def is_select_only(sql: str) -> bool:
    if FORBIDDEN.search(sql):
        return False
    parsed = sqlparse.parse(sql)
    if len(parsed) == 0:
        return False
    for stmt in parsed:
        # sqlparse sometimes marks complex queries as UNKNOWN → fallback to checking text
        stmt_type = stmt.get_type().upper() if stmt.get_type() else ""
        if stmt_type != "SELECT":
            return False
    return True

def enforce_limit(sql: str, limit: int = 1000) -> str:
    if re.search(r'\blimit\b', sql, re.I):
        return sql
    return sql.rstrip().rstrip(';') + f' LIMIT {limit};'

def run_sql(sql: str, limit: int = 1000) -> pd.DataFrame:
    if not is_select_only(sql):
        raise ValueError("Only SELECT queries are allowed.")
    safe_sql = enforce_limit(sql, limit)

    with engine.connect() as conn:
        result = conn.execute(text(safe_sql))  # ✅ always wrap in text()
        rows = result.fetchall()
        cols = result.keys()

    return pd.DataFrame(rows, columns=cols)
