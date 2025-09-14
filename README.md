# NL2SQL-HCL-PROJECT
Overview :
This app lets users ask questions in natural language about a defects dataset and get instant SQL queries and results. It uses a local SQLite database built from defects_data.csv and Google Gemini to convert natural language to SQL. 

Features: 
1. Accepts user queries in plain English.
2. Uses an LLM (Gemini API) to generate corresponding SQL queries.
3. Ensures queries are safe (only SELECT allowed, limit enforced).
4. Executes SQL on a SQLite database (defects.db) created from defects_data.csv.
5. Displays results interactively in the Streamlit UI.

API Key Setup:
This project uses the Gemini LLM API for natural language to SQL conversion.
Before running the application, you need to:

1. Generate an API key from Gemini.
2. Create a .env file in the project root directory and add the key.
