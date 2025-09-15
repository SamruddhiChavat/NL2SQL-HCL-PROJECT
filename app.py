import streamlit as st
from schema_utils import SchemaUtils
from llm_sql import GeminiSQL
from db_exec import DBExecutor

class NL2SQLApp:
    def __init__(self, db_path="defects.db"):
        self.schema = SchemaUtils(db_path)
        self.llm = GeminiSQL()
        self.db = DBExecutor(db_path)

        # Initializes chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []

    def run(self):
        st.set_page_config(page_title="NL → SQL Plugin", layout="centered")
        st.title("💬 NL → SQL Chatbot")

        # Clear chat button
        if st.button("🧹 Clear Chat"):
            st.session_state.messages = []
            st.rerun()

        # Shows schema in expander
        schema_texts = self.schema.all_schemas_to_text()
        with st.expander("📑 View schema"):
            st.text(schema_texts)

        # Renders previous messages
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if isinstance(msg["content"], str):
                    st.markdown(msg["content"])
                elif isinstance(msg["content"], dict):
                    if "text" in msg["content"]:
                        st.markdown(msg["content"]["text"])
                    if "dataframe" in msg["content"]:
                        st.dataframe(msg["content"]["dataframe"])

        # Chat input
        if user_q := st.chat_input("Ask me about the data in natural language…"):
            # Saves + shows user question
            st.session_state.messages.append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            try:
                # Generates SQL (+ notes when required)
                sql, note = self.llm.generate_sql(schema_texts, user_q)
                sql_preview = f"Here’s the SQL query:\n```sql\n{sql}\n```"

                st.session_state.messages.append({"role": "assistant", "content": sql_preview})
                with st.chat_message("assistant"):
                    st.markdown(sql_preview)

                # Executes SQL
                df = self.db.run_sql(sql, limit=200)
                if not df.empty:
                    result_msg = f"📊 Query returned {len(df)} rows:"
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": {"text": result_msg, "dataframe": df}
                    })

                    with st.chat_message("assistant"):
                        st.markdown(result_msg)
                        st.dataframe(df)
                else:
                    nores_msg = "⚠️ No results found."
                    st.session_state.messages.append({"role": "assistant", "content": nores_msg})
                    with st.chat_message("assistant"):
                        st.warning("No results found.")

                # Shows NOTE (if model gave one)
                if note:
                    st.session_state.messages.append({"role": "assistant", "content": note})
                    with st.chat_message("assistant"):
                        st.info(note)

            except Exception as e:
                err_msg = f"❌ Error: {e}"
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
                with st.chat_message("assistant"):
                    st.error(err_msg)


if __name__ == "__main__":
    app = NL2SQLApp()
    app.run()
