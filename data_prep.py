import pandas as pd
import sqlite3

def prepare_database(csv_file, db_file):
    df = pd.read_csv(csv_file)

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # Drops old tables if they exist
    cur.execute("DROP TABLE IF EXISTS defects")
    cur.execute("DROP TABLE IF EXISTS products")
    cur.execute("DROP TABLE IF EXISTS inspection_methods")

    # Creates new normalized tables
    cur.execute("""
        CREATE TABLE products (
            product_id TEXT PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE inspection_methods (
            method_id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_method TEXT,
            defect_location TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE defects (
            defect_id TEXT PRIMARY KEY,
            product_id TEXT,
            method_id INTEGER,
            defect_type TEXT,
            defect_date TEXT,
            severity TEXT,
            repair_cost FLOAT,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (method_id) REFERENCES inspection_methods(method_id)
        )
    """)

    # Inserts unique products
    products = df['product_id'].dropna().unique()
    cur.executemany("INSERT INTO products (product_id) VALUES (?)", [(p,) for p in products])

    # Inserts unique inspection methods with location
    inspection_pairs = df[['inspection_method', 'defect_location']].drop_duplicates()
    cur.executemany("INSERT INTO inspection_methods (inspection_method, defect_location) VALUES (?, ?)",
                    [tuple(row) for row in inspection_pairs.values])

    # Maps inspection_method + defect_location to method_id
    method_map = {}
    for row in cur.execute("SELECT method_id, inspection_method, defect_location FROM inspection_methods"):
        method_map[(row[1], row[2])] = row[0]

    # Inserts defects with proper foreign keys
    for _, row in df.iterrows():
        method_id = method_map.get((row['inspection_method'], row['defect_location']))
        cur.execute("""
            INSERT INTO defects (defect_id, product_id, method_id, defect_type, defect_date, severity, repair_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            row['defect_id'],
            row['product_id'],
            method_id,
            row['defect_type'],
            row['defect_date'],
            row['severity'],
            row['repair_cost']
        ))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    prepare_database("defects_data.csv", "defects.db")
