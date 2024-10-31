import pandas as pd
import sys
import pylcs

def get_line_size(text):
    return len(text.splitlines())

def get_lcs(text1,text2):
    res = pylcs.lcs_sequence_idx(text1, text2)
    lcs = ''.join([text2[i] for i in res if i != -1])
    return lcs

def get_gestalt(file1_text,file2_text):
    try:
        if file1_text == file2_text:
            return 1
        return 2*len(get_lcs(file1_text, file2_text)) / (len(file1_text) + len(file2_text))
    except Exception as e:
        print(e)
        return 0

if len(sys.argv) > 1:
    dataset_name = sys.argv[1]
    print("Dataset: ", dataset_name)
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
        if v1_size_char < 20000 and v2_size_char < 20000 and solution_size_char < 200000 :
            resolution_v1_sim = get_gestalt(solution, v1)
            resolution_v2_sim = get_gestalt(solution, v2)
            resolution_parents_sim = (resolution_v1_sim + resolution_v2_sim) / 2
        else:
            resolution_v1_sim = -1
            resolution_v2_sim = -1
            resolution_parents_sim = -1
        
        data.append([row['chunk_id'], chunk_size, solution_size, chunk_size_char, solution_size_char, v1_size_char, v2_size_char, v1_size, v2_size, resolution_v1_sim, resolution_v2_sim, resolution_parents_sim])
        
        count+=1
    columns = ['chunk_id', 'chunk_size', 'solution_size', 'chunk_size_char', 'solution_size_char', 'v1_size_char', 'v2_size_char', 'v1_size', 'v2_size', 'resolution_v1_sim', 'resolution_v2_sim', 'resolution_parents_sim']
    print(f"Saving stats file for dataset {dataset_name}. Total of analyzed rows: {len(data)}")
    pd.DataFrame(data, columns=columns).to_csv(f'data/{dataset_name}_stats.csv', index=False)
    