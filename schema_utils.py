'''
from sqlalchemy import create_engine, text

DB_PATH = "defects.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# Gets the table schema
def get_table_schema(table_name: str):
    with engine.connect() as conn:
        res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))  
        return res.fetchall()

# Converts the schema to text
def schema_to_text(table_name: str) -> str:
    cols = get_table_schema(table_name)
    schema_lines = []
    for col in cols:
        # PRAGMA returns: (cid, name, type, notnull, dflt_value, pk)
        name, col_type = col[1], col[2]
        schema_lines.append(f"- {name} ({col_type})")
    return "\n".join(schema_lines)
'''

# schema_utils.py

from sqlalchemy import create_engine, text


class SchemaUtils:
    def __init__(self, db_path: str):
        # Initialize database engine
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )

    def get_table_schema(self, table_name: str):
        """Fetch schema info for a given table using PRAGMA."""
        with self.engine.connect() as conn:
            res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))
            return res.fetchall()

    def schema_to_text(self, table_name: str) -> str:
        """Convert schema into formatted text for LLM prompt."""
        cols = self.get_table_schema(table_name)
        schema_lines = [f"- {col[1]} ({col[2]})" for col in cols]
        return "\n".join(schema_lines)
