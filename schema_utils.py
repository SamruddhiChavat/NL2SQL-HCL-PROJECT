# schema_utils.py
from sqlalchemy import create_engine, text

class SchemaUtils:
    def __init__(self, conn_or_path: str, db_type: str = "sqlite"):
        self.db_type = db_type.lower()
        if self.db_type == "sqlite":
            conn_str = f"sqlite:///{conn_or_path}"
            connect_args = {"check_same_thread": False}
        else:
            conn_str = conn_or_path
            connect_args = {}
        self.engine = create_engine(conn_str, connect_args=connect_args)

    def list_tables(self):
        with self.engine.connect() as conn:
            if self.db_type == "sqlite":
                res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                return [r[0] for r in res.fetchall()]
            else:
                res = conn.execute(text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE';"))
                return [r[0] for r in res.fetchall()]

    def get_table_schema(self, table_name: str):
        with self.engine.connect() as conn:
            if self.db_type == "sqlite":
                res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))
                rows = res.fetchall()
                return [{"cid": r[0], "name": r[1], "type": r[2], "notnull": r[3], "dflt_value": r[4], "pk": r[5]} for r in rows]
            else:
                res = conn.execute(text(
                    "SELECT ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT "
                    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :t;"), {"t": table_name})
                rows = res.fetchall()
                return [{"cid": r[0], "name": r[1], "type": r[2], "notnull": 0 if r[3] == 'YES' else 1, "dflt_value": r[4], "pk": 0} for r in rows]

    def schema_to_text(self, table_name: str) -> str:
        cols = self.get_table_schema(table_name)
        schema_lines = [f"- {col['name']} ({col['type']})" for col in cols]
        return f"Table: {table_name}\n" + "\n".join(schema_lines)

    def all_schemas_to_text(self) -> str:
        tables = self.list_tables()
        schemas = [self.schema_to_text(t) for t in tables]
        return "\n\n".join(schemas)