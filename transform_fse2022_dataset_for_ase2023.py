import os
import json
import pandas as pd

all_raw_base = []
all_raw_a = []
all_raw_b = []
all_raw_res = []
chunks_data = []

def extract_info_from_json(file_path, file_name):
    # global all_raw_base, all_raw_a, all_raw_b, all_raw_res
    global chunks_data
    with open(file_path, 'r') as file:
        data = json.load(file)
        merge_id = file_name.split('_')[0]
        conflicting_chunks = data.get('conflicting_chunks', [])
        chunk_number = 1
        for chunk in conflicting_chunks:
            if chunk.get('res_region', '') != None:
                chunks_data.append([chunk.get('base_contents', ''), chunk.get('a_contents', ''),chunk.get('b_contents', ''),  chunk.get('res_region', ''), merge_id, chunk_number])
            chunk_number+=1
            # all_raw_a.append(chunk.get('a_contents', ''))
            # all_raw_b.append(chunk.get('b_contents', ''))
            # all_raw_base.append(chunk.get('base_contents', ''))
            # all_raw_res.append(chunk.get('res_region', ''))
            
            
def list_json_files(folder_path):
    total_files = 1
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                print("Processing:", file_path, file)
                extract_info_from_json(file_path, file)
                total_files+=1

def write_result_file():
    with open('data/dataset2_complete.json', 'w') as file:
        file.write("{")
        file.write(f'\t "all_raw_base": {all_raw_base},')
        file.write(f'\t "all_raw_a": {all_raw_a},')
        file.write(f'\t "all_raw_b": {all_raw_b},')
        file.write(f'\t "all_raw_res": {all_raw_res}')
        file.write("}")

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
    # write_result_file()
    json_data = pd.DataFrame(chunks_data, columns=columns).to_dict(orient="list")
    with open("data/dataset2_complete.json", "w") as json_file:
        json.dump(json_data, json_file, indent=4)