import json
import pandas as pd
from multiset import Multiset
    
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
        v1 = row['all_raw_a']
        v2 = row['all_raw_b']
        resolution = row['all_raw_res']
        chunk_id = str(row['merge_id']) + '-' + str(row['chunk_number'])
        data.append([chunk_id, v1, v2, resolution, row['all_raw_base'], identify_resolution(v1, v2, resolution)])
        count+=1
    new_df = pd.DataFrame(data, columns=['chunk_id', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'all_raw_base', 'resolution_strategy'])
    df_combination =  new_df[new_df['resolution_strategy']=='Combination']
    df_dataset = df_combination[['chunk_id', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'all_raw_base']]
    return df_dataset

def save_dataset_to_json(dataset, file_name):
    json_data = dataset.to_dict(orient="list")
    with open(f"data/{file_name}", "w") as json_file:
        json.dump(json_data, json_file, indent=4)

def separate_datasets_combination(dataset_name):
    df_training = pd.read_json(f'data/{dataset_name}_training.json')
    df_training_combination = get_combination_chunks(df_training)
    save_dataset_to_json(df_training_combination, f'{dataset_name}_combination_training.json')

    df_testing = pd.read_json(f'data/{dataset_name}_testing.json')
    df_testing_combination = get_combination_chunks(df_testing)
    save_dataset_to_json(df_testing_combination, f'{dataset_name}_combination_testing.json')

    df_validation = pd.read_json(f'data/{dataset_name}_validation.json')
    df_validation_combination = get_combination_chunks(df_validation)
    save_dataset_to_json(df_validation_combination, f'{dataset_name}_combination_validation.json')

if __name__ == "__main__":
    separate_datasets_combination('dataset2')
    separate_datasets_combination('dataset2_Java')
    separate_datasets_combination('dataset2_CSharp')
    separate_datasets_combination('dataset2_JavaScript')
    separate_datasets_combination('dataset2_TypeScript')


    