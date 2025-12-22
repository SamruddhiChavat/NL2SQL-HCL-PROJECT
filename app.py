# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from llm_sql_local import LocalLLM
import os

# --------------------------------------------------
# 1. SQL SERVER CONNECTION
# --------------------------------------------------

# Correct fix: load from environment if available else fallback constant
MSSQL_CONN = os.getenv("MSSQL_CONN")
if MSSQL_CONN:
    CONN_STR = MSSQL_CONN
else:
    # DEFAULT working connection string
    CONN_STR = "mssql+pyodbc://sa:1234@localhost/olist?driver=ODBC+Driver+17+for+SQL+Server"

engine = create_engine(CONN_STR)

# --------------------------------------------------
# 2. EXTRACT SCHEMA FROM SQL SERVER (for RAG)
# --------------------------------------------------

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
            schema_lines.append("")  # blank line between tables

    return "\n".join(schema_lines)

SCHEMA_TEXT = extract_schema_text()

# --------------------------------------------------
# 3. INIT LLM WITH SCHEMA (RAG setup)
# --------------------------------------------------

llm = LocalLLM(db_type="mssql")
llm.set_schema(SCHEMA_TEXT)

# --------------------------------------------------
# 4. STREAMLIT UI
# --------------------------------------------------

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

        elif norm_q in {
            "show the first 50 customers", "show 50 customers", "list 50 customers"
        }:
            direct_sql = (
                "SELECT TOP 50 customer_id, customer_unique_id, "
                "customer_zip_code_prefix, customer_city, customer_state "
                "FROM customers ORDER BY customer_id;"
            )

        elif norm_q in {
            "show 100 products with their dimensions and weight",
            "show 100 products with dimensions and weight",
            "show 100 products",
        }:
            direct_sql = (
                "SELECT TOP 100 product_id, product_category_name, "
                "product_weight_g, product_length_cm, product_height_cm, product_width_cm "
                "FROM products ORDER BY product_id;"
            )

        elif norm_q in {
            "show 50 sellers with their city and state",
            "show the first 50 sellers",
            "show 50 sellers",
        }:
            direct_sql = (
                "SELECT TOP 50 seller_id, seller_city, seller_state "
                "FROM sellers ORDER BY seller_city, seller_state;"
            )

        elif norm_q in {
            "show 50 order items with product category and price",
            "show 50 order items with product category",
            "show 50 order items",
        }:
            direct_sql = (
                "SELECT TOP 50 oi.order_id, oi.product_id, "
                "p.product_category_name, oi.price, oi.freight_value "
                "FROM order_items oi JOIN products p ON oi.product_id = p.product_id "
                "ORDER BY oi.order_id;"
            )

        elif "customer city" in norm_q and "how many orders" in norm_q:
            direct_sql = (
                "SELECT TOP 200 c.customer_city, COUNT(o.order_id) AS OrderCount "
                "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
                "GROUP BY c.customer_city ORDER BY OrderCount DESC;"
            )

        elif "top 10 most expensive products" in norm_q:
            direct_sql = (
                "SELECT TOP 10 p.product_id, p.product_category_name, "
                "AVG(oi.price) AS AveragePrice "
                "FROM order_items oi JOIN products p ON oi.product_id = p.product_id "
                "GROUP BY p.product_id, p.product_category_name "
                "ORDER BY AveragePrice DESC;"
            )

        if direct_sql is None and "product categories" in norm_q:
            direct_sql = (
                "SELECT DISTINCT product_category_name "
                "FROM products WHERE product_category_name IS NOT NULL "
                "ORDER BY product_category_name;"
            )

        if direct_sql is None and norm_q in {
            "show all seller cities", "list all seller cities", "get all seller cities"
        }:
            direct_sql = (
                "SELECT DISTINCT seller_city, seller_state "
                "FROM sellers ORDER BY seller_state, seller_city;"
            )

        if direct_sql is None and norm_q.startswith("get all sellers from"):
            city_raw = user_q[len("get all sellers from"):].strip(" .?!")
            if city_raw:
                city_norm = (
                    city_raw.replace("ã", "a").replace("á", "a")
                            .replace("é", "e").replace("í", "i")
                            .replace("ó", "o").replace("ú", "u")
                )
                direct_sql = f"""
SELECT TOP 200 seller_id, seller_zip_code_prefix, seller_city, seller_state
FROM sellers
WHERE LOWER(seller_city) = LOWER('{city_raw}')
   OR LOWER(seller_city) = LOWER('{city_norm}');
"""

        if norm_q in {"connection info", "who am i connected to", "db info"}:
            with engine.connect() as conn:
                db_name = conn.execute(text("SELECT DB_NAME();")).scalar()
                server_name = conn.execute(text("SELECT @@SERVERNAME;")).scalar()
            msg = f"Connected to database '{db_name}' on server '{server_name}'."
            st.session_state.messages.append({"role": "assistant", "content": msg})
            with st.chat_message("assistant"):
                st.markdown(msg)
            st.stop()

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
