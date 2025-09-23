from sqlalchemy import create_engine, text

class SchemaUtils:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    def list_tables(self):
        """Return all table names in the database"""
        with self.engine.connect() as conn:
            res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
            return [row[0] for row in res.fetchall()]

    def get_table_schema(self, table_name: str):
        """Return raw schema info for a table"""
        with self.engine.connect() as conn:
            res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))
            return res.fetchall()

    def schema_to_text(self, table_name: str) -> str:
        """Convert one table's schema to human-readable text"""
        cols = self.get_table_schema(table_name)
        schema_lines = [f"- {col[1]} ({col[2]})" for col in cols]
        return f"Table: {table_name}\n" + "\n".join(schema_lines)

    def all_schemas_to_text(self) -> str:
        """Return schemas of all tables in the DB as formatted text"""
        tables = self.list_tables()
        schemas = [self.schema_to_text(t) for t in tables]
        return "\n\n".join(schemas)


def get_db_schema_text(db_path: str = "manufacturing.db") -> str:
    utils = SchemaUtils(db_path)
    return utils.all_schemas_to_text()
