import sqlite3
import pandas as pd
from llm_sql import GeminiSQL  # your SQL generator class
from schema_utils import get_db_schema_text

DB_PATH = "defects.db"
TESTSET_PATH = "test_cases.csv"

def execute_query(conn, query):
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description] if cursor.description else []
        df = pd.DataFrame(rows, columns=colnames)
        return df
    except Exception as e:
        return f"ERROR: {e}"

def compare_results(pred_df, gold_df):
    """Compare two dataframes ignoring row/column order."""
    if isinstance(pred_df, str):  # execution error
        return False
    try:
        return pred_df.reset_index(drop=True).equals(gold_df.reset_index(drop=True))
    except Exception:
        return False

def main():
    conn = sqlite3.connect(DB_PATH)
    schema_text = get_db_schema_text(DB_PATH)
    llm = GeminiSQL()

    # Load test cases
    test_cases = pd.read_csv(TESTSET_PATH)

    total = len(test_cases)
    exact_match = 0
    execution_success = 0
    result_match = 0

    for i, row in test_cases.iterrows():
        nl_query = row["question"]
        gold_sql = row["gold_sql"]
        gold_result = execute_query(conn, gold_sql)
        if isinstance(gold_result, str):  # error in gold query
            print(f"⚠️ Skipping case {i}, bad gold query.")
            continue

        try:
            pred_sql, note = llm.generate_sql(schema_text, nl_query)
            pred_result = execute_query(conn, pred_sql)

            # Check metrics
            if pred_sql.strip().lower() == gold_sql.strip().lower():
                exact_match += 1
            if not isinstance(pred_result, str):
                execution_success += 1
            if compare_results(pred_result, gold_result):
                result_match += 1

            print(f"\nQ: {nl_query}")
            print(f"Pred SQL: {pred_sql}")
            print(f"Gold SQL: {gold_sql}")
            print(f"Match: {compare_results(pred_result, gold_result)} | Note: {note}")

        except Exception as e:
            print(f"❌ Error for Q{i}: {e}")

    print("\n📊 Accuracy Report:")
    print(f"Exact SQL Match: {exact_match}/{total} = {exact_match/total:.2%}")
    print(f"Execution Success: {execution_success}/{total} = {execution_success/total:.2%}")
    print(f"Result Match: {result_match}/{total} = {result_match/total:.2%}")

    conn.close()

if __name__ == "__main__":
    main()
