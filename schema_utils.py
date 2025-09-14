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

from sqlalchemy import create_engine, text

import os
DB_PATH = os.path.join(os.path.dirname(__file__), "defects.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# Gets the table schema
def get_table_schema(table_name: str):
    with engine.connect() as conn:
        res = conn.execute(text(f"PRAGMA table_info('{table_name}');"))
        return res.fetchall()

# Converts the schema to text (for LLM prompt)
def schema_to_text(table_name: str) -> str:
    cols = get_table_schema(table_name)
    schema_lines = []
    for col in cols:
        # PRAGMA returns: (cid, name, type, notnull, dflt_value, pk)
        name, col_type = col[1], col[2]
        schema_lines.append(f"- {name} ({col_type})")
    return "\n".join(schema_lines)
