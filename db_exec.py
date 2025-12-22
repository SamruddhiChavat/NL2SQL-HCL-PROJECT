# db_exec.py
import re
import sqlparse
import pandas as pd
from sqlalchemy import create_engine, text
import os

class DBExecutor:
    def __init__(self, conn_or_path: str = None, db_type: str = "sqlite"):
        self.db_type = db_type.lower()
        if self.db_type == "sqlite":
            conn = f"sqlite:///{conn_or_path}"
            self.engine = create_engine(conn, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(conn_or_path)

        self.forbidden = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|grant|revoke|replace|merge)\b", re.I)

    def is_select_only(self, sql: str) -> bool:
        if self.forbidden.search(sql):
            return False
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False
        for stmt in parsed:
            t = stmt.get_type()
            if not t or t.upper() != "SELECT":
                return False
        return True

    def enforce_limit(self, sql: str, limit: int = 200) -> str:
        if self.db_type == "sqlite":
            if re.search(r"\blimit\b", sql, re.I):
                return sql
            return sql.rstrip().rstrip(";") + f" LIMIT {limit};"
        else:
            # MSSQL: add TOP N after SELECT if not present
            if re.search(r"\bTOP\s+\d+\b", sql, re.I) or re.search(r"\bOFFSET\b", sql, re.I):
                return sql
            return re.sub(r"^\s*SELECT\s", f"SELECT TOP {limit} ", sql, flags=re.I)

    def run_sql(self, sql: str, limit: int = 200) -> pd.DataFrame:
        if not self.is_select_only(sql):
            raise ValueError("Only SELECT queries are allowed.")
        safe_sql = self.enforce_limit(sql, limit)
        with self.engine.connect() as conn:
            df = pd.read_sql_query(text(safe_sql), conn)
        return df