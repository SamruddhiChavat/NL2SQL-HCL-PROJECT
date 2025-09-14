import sqlite3
import pandas as pd
import os
DB_PATH = os.path.join(os.path.dirname(__file__), "defects.db")


def run_query(query):
    conn = sqlite3.connect("test.db")
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df
