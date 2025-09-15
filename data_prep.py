# data_prep.py

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()


class DataPrep:
    def __init__(self, csv_path="defects_data.csv", db_path="defects.db", table_name="defects"):
        self.csv_path = csv_path
        self.db_path = db_path
        self.table_name = table_name

    def load_and_clean(self):
        df = pd.read_csv(self.csv_path, dtype=str)

        # Trim column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Parse defect_date
        if "defect_date" in df.columns:
            df["defect_date"] = pd.to_datetime(df["defect_date"], errors="coerce")
            df["defect_date"] = df["defect_date"].dt.strftime("%Y-%m-%d")

        # Convert repair_cost to numeric
        if "repair_cost" in df.columns:
            df["repair_cost"] = pd.to_numeric(df["repair_cost"], errors="coerce")

        # Normalize text columns
        text_cols = ["defect_type", "defect_location", "severity", "inspection_method", "product_id"]
        for c in text_cols:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip().replace({"nan": None})

        # Drop duplicates
        df = df.drop_duplicates()

        # Drop missing defect_id
        if "defect_id" in df.columns:
            df = df.dropna(subset=["defect_id"])

        # Fill missing severity
        if "severity" in df.columns:
            df["severity"] = df["severity"].fillna("Unknown")

        return df

    def create_sqlite(self, df):
        engine = create_engine(f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False})
        df.to_sql(self.table_name, engine, if_exists="replace", index=False)
        return f"Saved {len(df)} rows to {self.db_path} in table {self.table_name}"


if __name__ == "__main__":
    prep = DataPrep()
    df = prep.load_and_clean()
    print(prep.create_sqlite(df))
