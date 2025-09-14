import pandas as pd
import sqlite3

# Load the CSV file
df = pd.read_csv('defects_data.csv')

# Connect to SQLite (this creates data.db if it doesn't exist)
conn = sqlite3.connect('data.db')

# Write the DataFrame to a new table called 'defects'
df.to_sql('defects', conn, if_exists='replace', index=False)

print("defects_data.csv loaded into defects table in data.db")

# Close the connection
conn.close()
