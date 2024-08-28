import torch.utils.data as data
import pickle
import numpy as np
from tqdm import tqdm
import json
import os
import math
import pandas as pd
from transformers import RobertaTokenizer

model_type = 'Salesforce/codet5-small'
tokenizer = RobertaTokenizer.from_pretrained(model_type)
class dotdict(dict):
    def __getattr__(self, name):  
        return self[name]

space_token = 'Ġ'
args = dotdict({
    'lr':1e-4,
    'model_type':model_type,
    'max_conflict_length':300,
    'max_resolve_length':100,
})
class Dataset(data.Dataset):
    def __init__(self, args, tokenizer, partition_name, dataset_name):
        self.max_conflict_length = args.max_conflict_length
        self.max_resolve_length = args.max_resolve_length
        self.tokenizer = tokenizer


        data_path = f'PROCESSED/{dataset_name}/processed_{partition_name}.pkl'

        if not os.path.exists(data_path):
            raw_data_file = json.load(open(f'../data/{dataset_name}_complete.json'))
            all_raw_base = raw_data_file['all_raw_base']
            all_raw_a = raw_data_file['all_raw_a']
            all_raw_b = raw_data_file['all_raw_b']
            all_raw_res = raw_data_file['all_raw_res']

            self.process_data(all_raw_base, all_raw_a, all_raw_b, all_raw_res, partition_name, dataset_name)
        self.data = pickle.load(open(data_path, "rb"))


    def process_data(self, all_raw_base, all_raw_a, all_raw_b, all_raw_res,  partition_name="train", dataset_name="dataset1"):
        data_num = len(all_raw_base)
        each_num = 1000
        
        total_batches = []

        for i in tqdm(range(math.ceil(data_num / each_num))):
            cur_start = i * each_num
            cur_end = min((i + 1) * each_num, data_num)
            cur_data_path = f"PROCESSED/{dataset_name}/processed_{cur_start}_{cur_end}.pkl"
            self.ii = i
            cur_batches = pickle.load(open(cur_data_path, 'rb'))
            if len(total_batches) == 0:
                total_batches = cur_batches
            else:
                for i in range(len(total_batches)):
                    total_batches[i] = np.concatenate([total_batches[i], cur_batches[i]], axis = 0)


        print('all data num:%d remaining num:%d'%(data_num, len(total_batches[0])))
        assert data_num == len(total_batches[0])
        train_ratio = 0.8
        val_ratio = 0.1
        test_ratio = 0.1
        df = pd.DataFrame(all_raw_a)
        train_end = int(len(df) * train_ratio)
        val_end = train_end + int(len(df) * val_ratio)

        
        train_index = list(df.iloc[:train_end].index)
        valid_index = list(df.iloc[train_end:val_end].index)
        test_index = list(df.iloc[val_end:].index)

        all_index = {'train':train_index, 'valid': valid_index, 'test': test_index}
        json.dump(all_index, open(f'all_index_{dataset_name}','w'))
        
        train_batches = []
        valid_batches = []
        test_batches = []

        for i in range(len(total_batches)):
            train_batches.append(total_batches[i][train_index])
            valid_batches.append(total_batches[i][valid_index])
            test_batches.append(total_batches[i][test_index])
        print(f'train batches: {len(train_batches)}')
        print(f'valid batches: {len(valid_batches)}')
        print(f'test batches: {len(test_batches)}')
        pickle.dump(train_batches, open(f"PROCESSED/{dataset_name}/processed_train.pkl", 'wb'))
        pickle.dump(valid_batches, open(f"PROCESSED/{dataset_name}/processed_valid.pkl", 'wb'))
        pickle.dump(test_batches, open(f"PROCESSED/{dataset_name}/processed_test.pkl", 'wb'))


    def pad_length(self, tokens, max_length, pad_id):
        if len(tokens) <= max_length:
            tokens = tokens + [pad_id] * (max_length - len(tokens))
        else:
            tokens = tokens[:max_length]
        assert len(tokens) == max_length
        return tokens

    
    def __getitem__(self, offset):
        data = []
        for i in range(len(self.data)):
            if type(self.data[i][offset]) == np.ndarray:
                data.append(self.data[i][offset])
            else:
                data.append(self.data[i][offset].toarray())  
        return data
    def __len__(self):
        return len(self.data[0])




