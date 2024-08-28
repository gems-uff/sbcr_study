import pandas as pd
import os
import json

RANDOM_SEED = 27082024
dataset1_path = 'data/dataset1_complete.json'
dataset2_path = 'data/dataset2_complete.json'

def split_data(df, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1):
    df = df.sample(frac=1, random_state=RANDOM_SEED)
    
    train_end = int(len(df) * train_ratio)
    val_end = train_end + int(len(df) * val_ratio)
    
    training_data = df.iloc[:train_end]
    validation_data = df.iloc[train_end:val_end]
    testing_data = df.iloc[val_end:]
    
    return training_data, validation_data, testing_data

dataset1_df = pd.read_json(dataset1_path)
dataset2_df = pd.read_json(dataset2_path)

dataset1_train, dataset1_val, dataset1_test = split_data(dataset1_df)
dataset2_train, dataset2_val, dataset2_test = split_data(dataset2_df)

def save_json(df, path):
    df.to_json(path, orient='records', indent=4)

os.makedirs('data', exist_ok=True)

save_json(dataset1_train, 'data/dataset1_training.json')
save_json(dataset1_val, 'data/dataset1_validation.json')
save_json(dataset1_test, 'data/dataset1_testing.json')

save_json(dataset2_train, 'data/dataset2_training.json')
save_json(dataset2_val, 'data/dataset2_validation.json')
save_json(dataset2_test, 'data/dataset2_testing.json')

print("Datasets have been successfully split and saved.")
