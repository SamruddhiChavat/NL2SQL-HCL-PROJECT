import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# loads .env file
load_dotenv()

CSV_PATH = "defects_data.csv"
DB_PATH = "defects.db"
TABLE_NAME = "defects"

def load_and_clean(csv_path):
    df = pd.read_csv(csv_path, dtype=str) 
   
    print("Initial rows:", len(df))
    print(df.columns.tolist())

    # Trims column names and standardizes
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Parses date
    if 'defect_date' in df.columns:
        df['defect_date'] = pd.to_datetime(df['defect_date'], errors='coerce')
        df['defect_date'] = df['defect_date'].dt.strftime('%Y-%m-%d')
    # Converts repair_cost to numeric
    if 'repair_cost' in df.columns:
        df['repair_cost'] = pd.to_numeric(df['repair_cost'], errors='coerce')

    # Normalizes text columns (strip + replace multiple spaces)
    text_cols = ['defect_type', 'defect_location', 'severity', 'inspection_method', 'product_id']
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().replace({'nan': None})

    # Drops duplicates
    before = len(df)
    df = df.drop_duplicates()
    print(f"dropped {before - len(df)} duplicates")

    # Drop rows missing essential fields
    df = df.dropna(subset=['defect_id']) if 'defect_id' in df.columns else df

    # Fills missing severity
    if 'severity' in df.columns:
        df['severity'] = df['severity'].fillna('Unknown')

    return df

# Creates sqllite database
def create_sqlite(df, db_path, table_name):
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    df.to_sql(table_name, engine, if_exists="replace", index=False)
    print(f"Saved {len(df)} rows to {db_path} table {table_name}")

if __name__ == "__main__":
    df = load_and_clean(CSV_PATH)
    create_sqlite(df, DB_PATH, TABLE_NAME)
