import os
import json
import pandas as pd
from multiset import Multiset

class Chunk:
    def __init__(self, mergeId, language, fileName, repo, commitHash, chunk_index_merge,
                v1_size, v2_size, v1, v2, base, resolution, label): 
        self.mergeId = mergeId
        self.language = language
        self.file_name = fileName
        self.repo = repo
        self.commitHash = commitHash
        self.chunk_index_merge = chunk_index_merge
        self.v1_size = v1_size
        self.v2_size = v2_size
        self.v1 = v1
        self.v2 = v2
        self.base = base
        self.resolution = resolution
        self.label = label
    
    def get_chunk_record_line(self):
        return [self.mergeId, self.language, self.file_name, self.repo, self.commitHash, self.chunk_index_merge,
               self.v1_size, self.v2_size, self.v1, self.v2, self.base, self.resolution, self.label]
    
def get_chunk_columns():
    return ['mergeId', 'language', 'fileName', 'repo', 'commitHash', 'chunk_index_merge',
            'v1_size', 'v2_size', 'v1', 'v2', 'base', 'resolution', 'label']

def extract_info_from_json(file_path, chunks, file_name, language):
    with open(file_path, 'r') as file:
        data = json.load(file)
        merge_id = file_name.split('_')[0]
        fname = data.get('fname', '')
        repo = data.get('repo', '')
        commit_hash = data.get('commitHash', '')
        conflicting_chunks = data.get('conflicting_chunks', [])
        chunk_index_merge = 1
        for chunk in conflicting_chunks:
            sizes = chunk.get('sizes', {}).get('lines', {})
            size_a = sizes.get('a', '')
            size_b = sizes.get('b', '')
            a_contents = chunk.get('a_contents', '')
            b_contents = chunk.get('b_contents', '')
            base_contents = chunk.get('base_contents', '')
            res_region = chunk.get('res_region', '')
            label = chunk.get('label', '')
            if res_region != None:
                chunk_object = Chunk(merge_id, language, fname, repo, commit_hash, chunk_index_merge,
                             size_a, size_b, a_contents, b_contents, base_contents, res_region, label)
                chunks.append(chunk_object.get_chunk_record_line())
            chunk_index_merge+=1
            
def list_json_files(folder_path):
    chunks = []
    total_files = 1
    for root, dirs, files in os.walk(folder_path):
        language = os.path.basename(root)
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                print("Processing:", file_path)
                extract_info_from_json(file_path, chunks, file, language)
                total_files+=1
    return pd.DataFrame(chunks, columns=get_chunk_columns())
    # .to_json(orient='records').replace('\\/', '/')
    # print(formatted_json, file=open('dataset2_Java_all-info.json', 'w'))
                

def remove_empty_lines(lines):
    return [line for line in lines if line.strip()]

def identify_resolution(v1, v2, resolution):
    v1_lines = normalize_lines(remove_empty_lines(v1.splitlines()))
    v2_lines = normalize_lines(remove_empty_lines(v2.splitlines()))
    resolution_lines = normalize_lines(remove_empty_lines(resolution.splitlines()))

    if normalize_line(v1) == normalize_line(resolution):
        return 'V1'
    elif normalize_line(v2) == normalize_line(resolution):
        return 'V2'
    elif normalize_line(resolution) == normalize_line(v1) + normalize_line(v2):
        return 'ConcatV1V2'
    elif normalize_line(resolution) == normalize_line(v2) + normalize_line(v1):
        return 'ConcatV2V1'
    else:
        v1_ms = Multiset(v1_lines)
        v2_ms = Multiset(v2_lines)
        resolution_ms = Multiset(resolution_lines)
        if len(resolution_ms - (v1_ms + v2_ms)) > 0:
            return 'New code'
        elif len(resolution_lines) == 0:
            return 'None'
        else:
            return 'Combination'
        
def normalize_line(line):
    return line.replace(" ", "").replace("\t", "").replace("\n", "")

def normalize_lines(lines):
    normalized_lines = []
    for line in lines:
        normalized_lines.append(normalize_line(line))
    return normalized_lines

def get_combination_chunks(dataset):
    data = []
    count = 1
    for index, row in dataset.iterrows():
        v1 = row['v1']
        v2 = row['v2']
        resolution = row['resolution']
        chunk_id = str(row['mergeId']) + '-' + str(row['chunk_index_merge'])
        data.append([chunk_id, identify_resolution(v1, v2, resolution), row['label']])
        count+=1
    new_df = pd.DataFrame(data, columns=['chunk_id', 'new_label', 'original_label'])
    df_combination =  new_df[new_df['new_label']=='Combination']
    df_combination.merge(df, on='chunk_id', how='left')
    df_combination = df_combination.merge(df, on='chunk_id', how='left')
    df_dataset = df_combination[['chunk_id', 'v1', 'v2', 'resolution', 'base']]
    df_dataset.rename(columns={'v1': 'all_raw_a', 'v2': 'all_raw_b', 'resolution': 'all_raw_res', 'base': 'all_raw_base'}, inplace=True)
    return df_dataset

def save_dataset_to_json(dataset, file_name):
    json_data = dataset.to_dict(orient="list")
    with open(f"data/{file_name}", "w") as json_file:
        json.dump(json_data, json_file, indent=4)

if __name__ == "__main__":
    folder_path = "data/fse2022/automated-analysis-data/Java"
    df1 = list_json_files(folder_path)
    df1['chunk_id'] = df1['mergeId'].astype(str) + '-' + df1['chunk_index_merge'].astype(str)
    folder_path = "data/fse2022/automated-analysis-data/CSharp"
    df2 = list_json_files(folder_path)
    df2['chunk_id'] = df2['mergeId'].astype(str) + '-' + df2['chunk_index_merge'].astype(str)
    folder_path = "data/fse2022/automated-analysis-data/JavaScript"
    df3 = list_json_files(folder_path)
    df3['chunk_id'] = df3['mergeId'].astype(str) + '-' + df3['chunk_index_merge'].astype(str)
    folder_path = "data/fse2022/automated-analysis-data/TypeScript"
    df4 = list_json_files(folder_path)
    df4['chunk_id'] = df4['mergeId'].astype(str) + '-' + df4['chunk_index_merge'].astype(str)
    df = pd.concat([df1, df2, df3, df4])
    

    save_dataset_to_json(df1[['chunk_id', 'mergeId', 'language', 'fileName', 'repo', 'commitHash', 'chunk_index_merge']], 'dataset2_Java_metadata.json')
    save_dataset_to_json(df2[['chunk_id', 'mergeId', 'language', 'fileName', 'repo', 'commitHash', 'chunk_index_merge']], 'dataset2_CSharp_metadata.json')
    save_dataset_to_json(df3[['chunk_id', 'mergeId', 'language', 'fileName', 'repo', 'commitHash', 'chunk_index_merge']], 'dataset2_JavaScript_metadata.json')
    save_dataset_to_json(df4[['chunk_id', 'mergeId', 'language', 'fileName', 'repo', 'commitHash', 'chunk_index_merge']], 'dataset2_TypeScript_metadata.json')
    
    df_combination = get_combination_chunks(df)
    save_dataset_to_json(df_combination, 'dataset2_combination.json')

    df_java_combination = get_combination_chunks(df1)
    save_dataset_to_json(df_java_combination, 'dataset2_Java_combination.json')

    df_csharp_combination = get_combination_chunks(df2)
    save_dataset_to_json(df_csharp_combination, 'dataset2_CSharp_combination.json')

    df_javascript_combination = get_combination_chunks(df3)
    save_dataset_to_json(df_javascript_combination, 'dataset2_JavaScript_combination.json')

    df_typescript_combination = get_combination_chunks(df4)
    save_dataset_to_json(df_typescript_combination, 'dataset2_TypeScript_combination.json')
