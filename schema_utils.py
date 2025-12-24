# schema_utils.py

from sqlalchemy import create_engine, text


class SchemaUtils:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    def get_table_schema(self, table_name: str):
        with self.engine.connect() as conn:
            res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))
            return res.fetchall()

    def schema_to_text(self, table_name: str) -> str:
        cols = self.get_table_schema(table_name)
        schema_lines = [f"- {col[1]} ({col[2]})" for col in cols]
        return "\n".join(schema_lines)
