# eval.py
import csv
import time
import pandas as pd
from llm_sql import generate_sql_with_gemini
from schema_utils import schema_to_text
from db_exec import run_sql

SCHEMA_TEXT = schema_to_text('defects')  # adjust table name if needed
TEST_CASES_CSV = "test_cases.csv"        # format: id,nl,gold_sql,notes

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    # convert datetime to string (if any)
    for c in df2.select_dtypes(include=['datetime64[ns]']):
        df2[c] = df2[c].dt.strftime('%Y-%m-%d')
    # sort columns and rows to compare ignoring order
    df2 = df2.reindex(sorted(df2.columns), axis=1)
    if df2.shape[1] > 0:
        df2 = df2.sort_values(by=list(df2.columns)).reset_index(drop=True)
    # fill NaNs with empty string for stable comparison
    df2 = df2.fillna('')
    return df2

def compare_results(df1, df2):
    # both are normalized DataFrames
    if df1.shape != df2.shape:
        return False
    return df1.equals(df2)

def evaluate():
    rows = []
    total = 0
    exec_match = 0
    exact_sql_match = 0
    gen_error = 0
    exec_error = 0
    total_gen_time = 0.0
    total_exec_time = 0.0

    with open(TEST_CASES_CSV, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            total += 1
            nl = r['nl']
            gold_sql = r['gold_sql']
            notes = r.get('notes', '')
            result = {
                'id': r['id'], 'nl': nl, 'gold_sql': gold_sql, 'gen_sql': '', 
                'gen_error': '', 'exec_error': '', 'exec_match': False,
                'gen_time_s': None, 'exec_time_s': None
            }
            try:
                t0 = time.time()
                gen_sql = generate_sql_with_gemini(SCHEMA_TEXT, nl)
                gen_time = time.time() - t0
                result['gen_sql'] = gen_sql
                result['gen_time_s'] = round(gen_time, 3)
                total_gen_time += gen_time
            except Exception as e:
                result['gen_error'] = str(e)
                gen_error += 1
                rows.append(result)
                continue

            # exact SQL match check (string)
            if gen_sql.strip().lower() == gold_sql.strip().lower():
                exact_sql_match += 1

            # execute both and compare resultsets
            try:
                t1 = time.time()
                df_gen = run_sql(gen_sql, limit=2000)
                df_gold = run_sql(gold_sql, limit=2000)
                exec_time = time.time() - t1
                result['exec_time_s'] = round(exec_time, 3)
                total_exec_time += exec_time
                # normalize & compare
                n_gen = normalize_df(df_gen)
                n_gold = normalize_df(df_gold)
                is_match = compare_results(n_gen, n_gold)
                result['exec_match'] = is_match
                if is_match:
                    exec_match += 1
            except Exception as e:
                result['exec_error'] = str(e)
                exec_error += 1

            rows.append(result)

    # summary
    summary = {
        'total': total,
        'generated_error': gen_error,
        'execution_error': exec_error,
        'execution_match_count': exec_match,
        'exact_sql_match_count': exact_sql_match,
        'execution_accuracy': exec_match / total if total>0 else 0.0,
        'exact_sql_match_rate': exact_sql_match / total if total>0 else 0.0,
        'avg_gen_time_s': (total_gen_time / (total - gen_error)) if (total-gen_error)>0 else None,
        'avg_exec_time_s': (total_exec_time / (total - gen_error - exec_error)) if (total-gen_error-exec_error)>0 else None
    }

    # write results CSV
    out_df = pd.DataFrame(rows)
    out_df.to_csv("eval_results.csv", index=False)
    print("Summary:", summary)
    print("Detailed results written to eval_results.csv")

if __name__ == "__main__":
    evaluate()
