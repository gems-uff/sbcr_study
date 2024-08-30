import os
import json
import pandas as pd

all_raw_base = []
all_raw_a = []
all_raw_b = []
all_raw_res = []
chunks_data = []
chunks_data_language = []

def extract_info_from_json(file_path, file_name):
    # global all_raw_base, all_raw_a, all_raw_b, all_raw_res
    global chunks_data, chunks_data_language
    with open(file_path, 'r') as file:
        data = json.load(file)
        merge_id = file_name.split('_')[0]
        conflicting_chunks = data.get('conflicting_chunks', [])
        chunk_number = 1
        for chunk in conflicting_chunks:
            if chunk.get('res_region', '') != None:
                chunks_data.append([chunk.get('base_contents', ''), chunk.get('a_contents', ''),chunk.get('b_contents', ''),  chunk.get('res_region', ''), merge_id, chunk_number])
                chunks_data_language.append([chunk.get('base_contents', ''), chunk.get('a_contents', ''),chunk.get('b_contents', ''),  chunk.get('res_region', ''), merge_id, chunk_number])
            chunk_number+=1
            
            
def list_json_files(folder_path):
    global chunks_data_language
    chunks_data_language = []
    total_files = 1
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                language = root.split('/')[-1]
                print("Processing:", file_path, file)
                extract_info_from_json(file_path, file)
                total_files+=1
    write_result_file(f'dataset2_{language}_complete.json', chunks_data_language)

def write_result_file(file_name, data):
    json_data = pd.DataFrame(data, columns=columns).to_dict(orient="list")
    with open(f"data/{file_name}", "w") as json_file:
        json.dump(json_data, json_file, indent=4)

if __name__ == "__main__":
    columns = ['all_raw_base', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'merge_id', 'chunk_number']
    folder_path_java = "data/fse2022/automated-analysis-data/Java"
    folder_path_csharp = "data/fse2022/automated-analysis-data/CSharp"
    folder_path_javascript = "data/fse2022/automated-analysis-data/JavaScript"
    folder_path_typescript = "data/fse2022/automated-analysis-data/TypeScript"
    list_json_files(folder_path_java)
    list_json_files(folder_path_csharp)
    list_json_files(folder_path_javascript)
    list_json_files(folder_path_typescript)
    write_result_file('dataset2_complete.json', chunks_data)