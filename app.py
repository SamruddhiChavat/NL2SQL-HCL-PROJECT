import os
import re
import streamlit as st
from llm_sql_local import LocalLLM
from db_exec import DBExecutor
from schema_utils import SchemaUtils

#  SQL SERVER activate
os.environ["DB_TYPE"] = "mssql"
DB_TYPE = "mssql"

# SQL Server connect
MSSQL_CONN = os.getenv("MSSQL_CONN")
if not MSSQL_CONN:
    raise RuntimeError(
        "MSSQL_CONN env var not set!\n"
        "Set it first: $env:MSSQL_CONN='mssql+pyodbc://sa:1234@localhost/olist?driver=ODBC+Driver+17+for+SQL+Server'"
    )

# Setup SQL Server connections
schema_util = SchemaUtils(MSSQL_CONN, db_type="mssql")
llm = LocalLLM(db_type="mssql")  # SQL Server aware
db = DBExecutor(conn_or_path=MSSQL_CONN, db_type="mssql")
conn_info = "✅ Using SQL Server (your migrated olist database)"

class NL2SQLApp:
    def __init__(self):
        # schema_text used for prompts and displayed to user
        self.schema_text = schema_util.all_schemas_to_text()
        # LLM will set its internal schema when generate_sql is called,
        # but set it explicitly once so it's parsed early (helps performance).
        try:
            llm.set_schema(self.schema_text)
        except Exception:
            # older versions or different LLM impls might not have set_schema; ignore safely
            pass
        self.llm = llm
        self.db = db

    def run(self):
        if "messages" not in st.session_state:
            st.session_state.messages = []

        st.set_page_config(page_title="NL → SQL (SQL Server)", layout="centered")
        st.title("🗄 NL → SQL Chatbot (SQL Server)")

        st.markdown(f"*Connection:* {conn_info}")
        with st.expander("🔍 View SQL Server schema (click to expand)"):
            st.text(self.schema_text)

        
        if st.button("🗑 Clear Chat"):
            st.session_state.messages = []

        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if isinstance(msg["content"], str):
                    st.markdown(msg["content"])
                elif isinstance(msg["content"], dict):
                    if "text" in msg["content"]:
                        st.markdown(msg["content"]["text"])
                    if "dataframe" in msg["content"]:
                        st.dataframe(msg["content"]["dataframe"])

        
        if user_q := st.chat_input("Ask me in natural language about your SQL Server data…"):
            st.session_state.messages.append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            try:
                # Generate SQL 
                sql = self.llm.generate_sql(self.schema_text, user_q, result_limit=200)

                
                sql_preview = f"*Generated SQL:*\n```sql\n{sql}\n```"
                st.session_state.messages.append({"role": "assistant", "content": sql_preview})
                with st.chat_message("assistant"):
                    st.markdown(sql_preview)

                
                try:
                    df = self.db.run_sql(sql, limit=200)
                    if df is not None and not df.empty:
                        result_msg = f"✅ Query returned *{len(df)} rows* from SQL Server:"
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": {"text": result_msg, "dataframe": df}
                        })
                        with st.chat_message("assistant"):
                            st.markdown(result_msg)
                            st.dataframe(df, use_container_width=True)
                    else:
                        nores_msg = "❌ No results found."
                        st.session_state.messages.append({"role": "assistant", "content": nores_msg})
                        with st.chat_message("assistant"):
                            st.warning(nores_msg)
                except Exception as db_err:
                    err_text = f"❌ Database error: {db_err}"
                    st.session_state.messages.append({"role": "assistant", "content": err_text})
                    with st.chat_message("assistant"):
                        st.error(err_text)

            except Exception as e:
                err_msg = f"❌ Error generating SQL: {e}"
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
                with st.chat_message("assistant"):
                    st.error(err_msg)

if __name__ == "__main__":
    app = NL2SQLApp()
    app.run()
