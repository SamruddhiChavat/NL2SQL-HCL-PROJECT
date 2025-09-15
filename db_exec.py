# db_exec.py

import re
import sqlparse
import pandas as pd
from sqlalchemy import create_engine, text

class DBExecutor:
    def __init__(self, db_path="defects.db", table="defects"):
        self.db_path = db_path
        self.table = table
        self.engine = create_engine(f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False})

        self.forbidden = re.compile(
            r'\b(insert|update|delete|drop|alter|create|truncate|attach|detach|grant|revoke|replace|merge)\b',
            re.I
        )

    def is_select_only(self, sql: str) -> bool:
        if self.forbidden.search(sql):
            return False
        parsed = sqlparse.parse(sql)
        if len(parsed) == 0:
            return False
        for stmt in parsed:
            stmt_type = stmt.get_type().upper() if stmt.get_type() else ""
            if stmt_type != "SELECT":
                return False
        return True

    def enforce_limit(self, sql: str, limit: int = 1000) -> str:
        if re.search(r'\blimit\b', sql, re.I):
            return sql
        return sql.rstrip().rstrip(';') + f' LIMIT {limit};'

    def run_sql(self, sql: str, limit: int = 1000) -> pd.DataFrame:
        if not self.is_select_only(sql):
            raise ValueError("Only SELECT queries are allowed.")
        safe_sql = self.enforce_limit(sql, limit)

        with self.engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            rows = result.fetchall()
            cols = result.keys()

        return pd.DataFrame(rows, columns=cols)
