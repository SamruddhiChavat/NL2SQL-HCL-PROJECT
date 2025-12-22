# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from llm_sql_local import LocalLLM
import os


MSSQL_CONN = os.getenv("MSSQL_CONN")
if MSSQL_CONN:
    CONN_STR = MSSQL_CONN
else:
    CONN_STR = (
    "mssql+pyodbc://sa:1234@localhost/olist"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)


engine = create_engine(CONN_STR)




def extract_schema_text() -> str:
    schema_lines = []
    with engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT TABLE_NAME "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME;"
        )).fetchall()

        for (table_name,) in tables:
            schema_lines.append(f"Table: {table_name}")
            cols = conn.execute(text(
                "SELECT COLUMN_NAME, DATA_TYPE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = :t "
                "ORDER BY ORDINAL_POSITION;"
            ), {"t": table_name}).fetchall()

            for col_name, data_type in cols:
                schema_lines.append(f"- {col_name} ({data_type})")
            schema_lines.append("")

    return "\n".join(schema_lines)


SCHEMA_TEXT = extract_schema_text()



llm = LocalLLM(db_type="mssql")
llm.set_schema(SCHEMA_TEXT)



st.set_page_config(page_title="NL → SQL Chatbot", layout="centered")
st.title("NL → SQL Chatbot (SQL Server / RAG over Schema)")
st.markdown("Connection: SQL Server database `olist` on `SQLEXPRESS`.")

with st.expander("View extracted SQL Server schema"):
    st.text(SCHEMA_TEXT)

if "messages" not in st.session_state:
    st.session_state.messages = []

if st.button("Clear Chat", key="clear_chat_button"):
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if isinstance(content, str):
            st.markdown(content)
        else:
            st.markdown(content["text"])
            st.dataframe(content["dataframe"], width="stretch")




user_q = st.chat_input("Ask a question about the olist data (natural language)")
if user_q:
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    try:
        norm_q = user_q.strip().lower()
        norm_q = norm_q.rstrip(".?!")

        direct_sql = None


       
        if norm_q in {"show all products", "list all products", "get all products"}:
            direct_sql = "SELECT TOP 200 * FROM products;"

        elif norm_q in {"show all orders", "list all orders", "get all orders"}:
            direct_sql = "SELECT TOP 200 * FROM orders;"

        elif norm_q in {"show all customers", "list all customers", "get all customers"}:
            direct_sql = "SELECT TOP 200 * FROM customers;"


        
        if direct_sql is None and ("customer" in norm_q and "city" in norm_q):
            direct_sql = """
SELECT DISTINCT customer_city, customer_state
FROM customers
WHERE customer_city IS NOT NULL
ORDER BY customer_city;
"""


       
        if direct_sql is None and ("seller" in norm_q and "city" in norm_q):
            direct_sql = """
SELECT DISTINCT seller_city, seller_state
FROM sellers
WHERE seller_city IS NOT NULL
ORDER BY seller_city;
"""


       
        if direct_sql is None and ("delivered" in norm_q):
            direct_sql = """
SELECT TOP 200 *
FROM orders
WHERE order_status = 'delivered';
"""


        if direct_sql is None and ("weight" in norm_q or "gram" in norm_q):
            direct_sql = """
SELECT TOP 200 *
FROM products
WHERE product_weight_g IS NOT NULL
ORDER BY product_weight_g DESC;
"""


       
        if direct_sql is None and "customers from" in norm_q:
            try:
                city = user_q.lower().split("from")[1].strip()
                direct_sql = f"""
SELECT TOP 200 *
FROM customers
WHERE LOWER(customer_city) = LOWER('{city}');
"""
            except:
                pass


        if direct_sql is None and "product categories" in norm_q:
            direct_sql = """
SELECT DISTINCT product_category_name
FROM products
WHERE product_category_name IS NOT NULL
ORDER BY product_category_name;
"""


        
        if direct_sql is not None:
            sql = direct_sql
        else:
            sql = llm.generate_sql(SCHEMA_TEXT, user_q, result_limit=200)


        
        sql_preview = f"Generated SQL:\n```sql\n{sql}\n```"
        st.session_state.messages.append({"role": "assistant", "content": sql_preview})

        with st.chat_message("assistant"):
            st.markdown(sql_preview)

        with engine.connect() as conn:
            df = pd.read_sql_query(text(sql), conn)

        result_content = {"text": f"Query returned {len(df)} rows.", "dataframe": df}
        st.session_state.messages.append({"role": "assistant", "content": result_content})

        with st.chat_message("assistant"):
            st.markdown(f"Query returned {len(df)} rows.")
            st.dataframe(df, width="stretch")

    except Exception as e:
        err_msg = f"Error: {e}"
        st.session_state.messages.append({"role": "assistant", "content": err_msg})
        with st.chat_message("assistant"):
            st.error(err_msg)
