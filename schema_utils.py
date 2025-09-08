# schema_utils.py
from sqlalchemy import create_engine, text

DB_PATH = "defects.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

def get_table_schema(table_name: str):
    with engine.connect() as conn:
        res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))  # ✅ wrap in text()
        return res.fetchall()

def schema_to_text(table_name: str) -> str:
    cols = get_table_schema(table_name)
    schema_lines = []
    for col in cols:
        # PRAGMA returns: (cid, name, type, notnull, dflt_value, pk)
        name, col_type = col[1], col[2]
        schema_lines.append(f"- {name} ({col_type})")
    return "\n".join(schema_lines)
