'''
import streamlit as st
from schema_utils import schema_to_text
from llm_sql import generate_sql_with_gemini
from db_exec import run_sql

# Displays the page title
st.set_page_config(page_title="NL → SQL Queries - POC", layout="wide")
st.title("NL → SQL — defects_data POC")

# Displays the database schema
schema_text = schema_to_text('defects')
st.markdown("Database Schema:")
st.text(schema_text)

user_q = st.text_input("Enter your query about defects here in natural language")

# The 'generate sql' button
if st.button("Generate SQL & Execute"):
    if not user_q.strip():
        st.error("Enter a question.")
    else:
        try:
            # 1. Generates SQL
            sql = generate_sql_with_gemini(schema_text, user_q)
            st.subheader("Generated SQL Query:")
            st.code(sql, language="sql")

            # 2. Executes the generated SQL Query
            df = run_sql(sql, limit=500)

            # 3. Shows result count
            st.success(f"Rows returned: {len(df)}")

            # 4. If single value (COUNT, AVG, SUM) shows as metric
            if df.shape[0] == 1 and df.shape[1] == 1:
                value = df.iat[0, 0]
                st.metric(label="Answer", value=value)
            else:
                st.dataframe(df)

        except Exception as e:
            st.error(str(e))
            '''

import streamlit as st
from schema_utils import schema_to_text
from llm_sql_local import LocalLLM
from db_exec import run_sql
import os
st.text(f"DB used: {os.path.join(os.path.dirname(__file__), 'defects.db')}")

TABLE_NAME = "defects"

# Get schema from the actual DB
schema_text = schema_to_text(TABLE_NAME)

# Initialize LLM
llm = LocalLLM(model="llama3")

st.title("NL2SQL - Local LLM Demo")

st.markdown("**Schema:**")
st.text(schema_text)

user_question = st.text_input("Ask me a question (e.g., Show all defects):")

if st.button("Generate SQL"):
    if not user_question.strip():
        st.error("Enter a question.")
    else:
        try:
            # Generate SQL from the LLM using real schema
            sql_query = llm.generate_sql(schema_text, user_question)
            st.subheader("Generated SQL")
            st.code(sql_query, language="sql")

            # Execute SQL
            results = run_sql(sql_query)
            st.subheader("Query Results")
            st.dataframe(results)

        except Exception as e:
            st.error(f"Error running query: {e}")
