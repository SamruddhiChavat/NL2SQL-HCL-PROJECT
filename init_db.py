import pandas as pd
import sqlite3

# Load the CSV
csv_path = "defects_data.csv"
df = pd.read_csv(csv_path)

# Clean up column names (just in case)
df.columns = [c.strip() for c in df.columns]

# Convert defect_date to proper ISO format (YYYY-MM-DD)
df["defect_date"] = pd.to_datetime(df["defect_date"], errors="coerce").dt.strftime("%Y-%m-%d")

# Save into SQLite DB
db_path = "defects.db"
conn = sqlite3.connect(db_path)
df.to_sql("defects", conn, if_exists="replace", index=False)
conn.close()

print(f"Database created successfully at {db_path} with table 'defects'.")