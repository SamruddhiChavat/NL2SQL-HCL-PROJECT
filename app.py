# app.py
import streamlit as st
from llm_sql_local import LocalLLM
from db_exec import DBExecutor
from schema_utils import SchemaUtils
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "defects.db")
schema_utils = SchemaUtils(DB_PATH)

schema_text = schema_utils.schema_to_text("defects")


class NL2SQLApp:
    def __init__(self, db_path="defects.db", table="defects"):
        self.schema = SchemaUtils(db_path)
        self.llm = LocalLLM(model="llama3")
        self.db = DBExecutor(db_path, table)
        self.table = table

        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []

    def run(self):
        st.set_page_config(page_title="NL to SQL", layout="centered")
        st.title("NL to SQL Chatbot")

        # Clear chat button
        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.rerun()

        # Show schema in expander
        schema_text = self.schema.schema_to_text(self.table)
        with st.expander("View schema"):
            st.text(schema_text)

        # Render previous messages
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat input
        if user_q := st.chat_input("Ask me in natural language…"):
            # Save + show user question
            st.session_state.messages.append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            try:
                # Generate SQL
                sql = self.llm.generate_sql(schema_text, user_q)
                sql_preview = f"Generated SQL:\n```sql\n{sql}\n```"

                st.session_state.messages.append({"role": "assistant", "content": sql_preview})
                with st.chat_message("assistant"):
                    st.markdown(sql_preview)

                # Execute SQL
                df = self.db.run_sql(sql, limit=200)
                if not df.empty:
                    result_msg = f"Query returned {len(df)} rows:"
                    st.session_state.messages.append({"role": "assistant", "content": result_msg})

                    with st.chat_message("assistant"):
                        st.markdown(result_msg)
                        st.dataframe(df)
                else:
                    nores_msg = "No results found."
                    st.session_state.messages.append({"role": "assistant", "content": nores_msg})
                    with st.chat_message("assistant"):
                        st.warning("No results found.")

            except Exception as e:
                err_msg = f"Error: {e}"
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
                with st.chat_message("assistant"):
                    st.error(err_msg)


if __name__ == "__main__":
    app = NL2SQLApp()
    app.run()
