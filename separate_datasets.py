import json
import random
import os

dataset1_path = 'data/dataset1_complete.json'
dataset2_path = 'data/dataset2_complete.json'

with open(dataset1_path, 'r') as f:
    dataset1 = json.load(f)

with open(dataset2_path, 'r') as f:
    dataset2 = json.load(f)

def split_data(data, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1):
    random.shuffle(data)
    total = len(data)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)
    
    training_data = data[:train_end]
    validation_data = data[train_end:val_end]
    testing_data = data[val_end:]
    
    return training_data, validation_data, testing_data

dataset1_train, dataset1_val, dataset1_test = split_data(dataset1)
dataset2_train, dataset2_val, dataset2_test = split_data(dataset2)

def save_json(data, path):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

os.makedirs('data', exist_ok=True)

save_json(dataset1_train, 'data/dataset1_training.json')
save_json(dataset1_val, 'data/dataset1_validation.json')
save_json(dataset1_test, 'data/dataset1_testing.json')

save_json(dataset2_train, 'data/dataset2_training.json')
save_json(dataset2_val, 'data/dataset2_validation.json')
save_json(dataset2_test, 'data/dataset2_testing.json')

print("Datasets have been successfully split and saved.")
