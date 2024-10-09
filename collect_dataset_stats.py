import pandas as pd
import sys

def get_line_size(text):
    return len(text.splitlines())

if len(sys.argv) > 1:
    dataset_name = sys.argv[1]

    df_chunks = pd.read_json(f'data/{dataset_name}.json')
    data = []
    count = 1
    if 'chunk_id' not in df_chunks.columns:
        df_chunks['chunk_id'] = df_chunks['merge_id'].astype(str)+'-'+df_chunks['chunk_number'].astype(str)

    for index, row in df_chunks.iterrows():
        print(f"Analyzing chunk ({row['chunk_id']}) {count} of {len(df_chunks)}", flush=True)
        v1 = row['all_raw_a']
        v2 = row['all_raw_b']
        solution = row['all_raw_res']
        
        if solution != None:
            solution_size = get_line_size(solution)
            solution_size_char = len(solution)
        else:
            solution_size = 0
            solution_size_char = 0
        chunk_size = get_line_size(v1) + get_line_size(v2)
        chunk_size_char = len(v1) + len(v2)
        v1_size = get_line_size(v1)
        v2_size = get_line_size(v2)
        v1_size_char = len(v1)
        v2_size_char = len(v2)
        
        data.append([row['chunk_id'], chunk_size, solution_size, chunk_size_char, solution_size_char, v1_size_char, v2_size_char, v1_size, v2_size])
        
        count+=1
    columns = ['chunk_id', 'chunk_size', 'solution_size', 'chunk_size_char', 'solution_size_char', 'v1_size_char', 'v2_size_char', 'v1_size', 'v2_size']
    pd.DataFrame(data, columns=columns).to_csv(f'data/{dataset_name}_stats.csv', index=False)
    