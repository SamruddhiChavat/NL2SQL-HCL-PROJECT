import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
import random

load_dotenv()

class DataPrep:
    def __init__(self, csv_path="defects_data.csv", db_path="defects.db"):
        self.csv_path = csv_path
        self.db_path = db_path

    def load_and_clean(self):
        df = pd.read_csv(self.csv_path, dtype=str)

        # Trim column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Normalize product_id globally (avoid join mismatches)
        if 'product_id' in df.columns:
            df['product_id'] = df['product_id'].astype(str).str.strip().str.upper()

        # Parse defect_date
        if 'defect_date' in df.columns:
            df['defect_date'] = pd.to_datetime(df['defect_date'], errors='coerce')
            df['defect_date'] = df['defect_date'].dt.strftime('%Y-%m-%d')

        # repair_cost numeric
        if 'repair_cost' in df.columns:
            df['repair_cost'] = pd.to_numeric(df['repair_cost'], errors='coerce')

        # normalize text columns (besides product_id which we already handled)
        text_cols = ['defect_type', 'defect_location', 'severity', 'inspection_method']
        for c in text_cols:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip().replace({'nan': None})

        # drop duplicates
        df = df.drop_duplicates()

        # drop missing defect_id
        if 'defect_id' in df.columns:
            df = df.dropna(subset=['defect_id'])

        # fill missing severity
        if 'severity' in df.columns:
            df['severity'] = df['severity'].fillna('Unknown')

        return df

    def create_sqlite(self, df):
        engine = create_engine(f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False})

        # ---- Create products table ----
        unique_products = df[['product_id']].drop_duplicates().copy()
        product_lines = ['Line A', 'Line B', 'Line C']
        manufacturers = ['Acme Corp', 'Globex Inc', 'Umbrella Co']

        # Add dummy data
        unique_products['product_line'] = [random.choice(product_lines) for _ in range(len(unique_products))]
        unique_products['manufacturer'] = [random.choice(manufacturers) for _ in range(len(unique_products))]

        unique_products.to_sql('products', engine, if_exists='replace', index=False)

        # ---- Create inspection_methods table ----
        unique_methods = df[['inspection_method', 'defect_location']].drop_duplicates().copy()
        unique_methods.rename(columns={'defect_location': 'default_location'}, inplace=True)
        unique_methods.to_sql('inspection_methods', engine, if_exists='replace', index=False)

        # ---- Update defects table ----
        defects_cols = ['defect_id', 'product_id', 'defect_type', 'defect_date',
                        'defect_location', 'severity', 'inspection_method', 'repair_cost']
        defects_df = df[defects_cols].copy()
        defects_df.to_sql('defects', engine, if_exists='replace', index=False)

        return f"Database created with {len(defects_df)} defects, {len(unique_products)} products, {len(unique_methods)} inspection methods."

if __name__ == "__main__":
    prep = DataPrep()
    df = prep.load_and_clean()
    print(prep.create_sqlite(df))
