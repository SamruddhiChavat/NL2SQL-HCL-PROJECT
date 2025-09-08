import streamlit as st
from schema_utils import schema_to_text
from llm_sql import generate_sql_with_gemini
from db_exec import run_sql

st.set_page_config(page_title="NL → SQL (defects) POC", layout="wide")
st.title("NL → SQL — defects_data POC")

schema_text = schema_to_text('defects')
st.markdown("**Schema:**")
st.text(schema_text)

user_q = st.text_input("Ask a question about defects (natural language):")

if st.button("Generate SQL & Execute"):
    if not user_q.strip():
        st.error("Enter a question.")
    else:
        try:
            # 1. Generate SQL
            sql = generate_sql_with_gemini(schema_text, user_q)
            st.subheader("Generated SQL")
            st.code(sql, language="sql")

            # 2. Execute SQL immediately
            df = run_sql(sql, limit=500)

            # 3. Show result count
            st.success(f"✅ Rows returned: {len(df)}")

            # 4. If single value (COUNT, AVG, SUM) show as metric
            if df.shape[0] == 1 and df.shape[1] == 1:
                value = df.iat[0, 0]
                st.metric(label="Answer", value=value)
            else:
                st.dataframe(df)

        except Exception as e:
            st.error(str(e))
