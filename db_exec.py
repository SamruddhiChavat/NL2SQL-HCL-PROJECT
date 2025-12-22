# db_exec.py
import re
import sqlparse
import pandas as pd
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)

class DBExecutor:
    def __init__(self, conn_str: str, db_type: str = "mssql"):
        """
        Initialize DBExecutor.

        :param conn_str: SQLAlchemy connection string (e.g., MSSQL)
        :param db_type: "mssql" or "sqlite"
        """
        self.db_type = db_type.lower()
        self.engine = create_engine(conn_str)
        # Regex to prevent dangerous queries
        self.forbidden = re.compile(
            r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|grant|revoke|replace|merge)\b",
            re.I
        )

    def is_select_only(self, sql: str) -> bool:
        """
        Check if query is SELECT-only.
        """
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
        """
        Add TOP N for SQL Server if not present.
        """
        if self.db_type == "mssql":
            # Skip if TOP N already exists
            if re.search(r"\bTOP\s+\d+\b", sql, re.I):
                return sql
            # Insert TOP N after first SELECT
            sql_fixed = re.sub(r"^\s*SELECT\s", f"SELECT TOP {limit} ", sql, flags=re.I)
            return sql_fixed
        else:
            # SQLite
            if re.search(r"\blimit\b", sql, re.I):
                return sql
            return sql.rstrip().rstrip(";") + f" LIMIT {limit};"

    def run_sql(self, sql: str, limit: int = 200) -> pd.DataFrame:
        """
        Execute a safe SELECT query and return DataFrame.
        """
        logging.info(f"Original SQL:\n{sql}")
        if not self.is_select_only(sql):
            raise ValueError("Only SELECT queries are allowed.")
        safe_sql = self.enforce_limit(sql, limit)
        logging.info(f"Executing SQL:\n{safe_sql}")
        with self.engine.connect() as conn:
            df = pd.read_sql_query(text(safe_sql), conn)
        return df
