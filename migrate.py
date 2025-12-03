import pandas as pd
import sqlite3
from sqlalchemy import create_engine
import os

SQLITE_PATH = "olist.sqlite"
MSSQL_CONN = os.getenv("MSSQL_CONN")

if not MSSQL_CONN:
    raise RuntimeError("MSSQL_CONN environment variable not set.")

sqlite_con = sqlite3.connect(SQLITE_PATH)
mssql_engine = create_engine(MSSQL_CONN)

tables = sqlite_con.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()

for (table,) in tables:
    print(f"Migrating {table}...")
    df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_con)
    df.to_sql(table, mssql_engine, if_exists="replace", index=False, chunksize=5000)
    print(f"Done {table}")

sqlite_con.close()
print("Migration complete!")






