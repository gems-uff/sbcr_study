import torch.utils.data as data
import pickle
import numpy as np
from tqdm import tqdm
import json
import os
import math
import pandas as pd
from transformers import RobertaTokenizer

RANDOM_SEED = 27082024
# model_type = 'Salesforce/codet5-small'
model_type='./codet5-small-local'
tokenizer = RobertaTokenizer.from_pretrained(model_type)
def chunk_identifiers(raw_data_file):
    """The chunk_id of each row, when the data file has it."""
    if 'chunk_id' in raw_data_file:
        return [str(c) for c in raw_data_file['chunk_id']]
    if 'merge_id' in raw_data_file and 'chunk_number' in raw_data_file:
        return [f'{m}-{c}' for m, c in zip(raw_data_file['merge_id'], raw_data_file['chunk_number'])]
    return None


def partitions(dataset_name, all_raw_a, chunk_ids):
    """Reads the assignment chunk_id -> partition of `../data/split_<dataset>.csv`.

    Without that file, the split is drawn here at random, as in the original code.
    """
    path = f'../data/split_{dataset_name}.csv'
    if chunk_ids is not None and os.path.exists(path):
        assignment = pd.read_csv(path, dtype={'chunk_id': str})
        assignment = dict(zip(assignment.chunk_id, assignment.partition))
        missing = [c for c in chunk_ids if c not in assignment]
        if missing:
            raise ValueError(f'{len(missing)} chunks without a partition in {path}, the first is {missing[0]}')
        print(f'explicit split: {path}')
        indices = {'train': [], 'validation': [], 'test': []}
        for i, c in enumerate(chunk_ids):
            indices[assignment[c]].append(i)
        return indices['train'], indices['validation'], indices['test']

    print(f'no {path}: drawing the split at random with seed {RANDOM_SEED}')
    df = pd.DataFrame(all_raw_a).sample(frac=1, random_state=RANDOM_SEED)
    train_end = int(len(df) * 0.8)
    val_end = train_end + int(len(df) * 0.1)
    return (list(df.iloc[:train_end].index),
            list(df.iloc[train_end:val_end].index),
            list(df.iloc[val_end:].index))


class dotdict(dict):
    def __getattr__(self, name):  
        return self[name]

space_token = 'Ġ'
args = dotdict({
    'lr':1e-4,
    'model_type':model_type,
    'max_conflict_length':500,
    'max_resolve_length':200,
})
class Dataset(data.Dataset):
    def __init__(self, args, tokenizer, partition_name, dataset_name):
        self.max_conflict_length = args.max_conflict_length
        self.max_resolve_length = args.max_resolve_length
        self.tokenizer = tokenizer


        data_path = f'PROCESSED/{dataset_name}/processed_{partition_name}.pkl'

        if not os.path.exists(data_path):
            raw_data_file = json.load(open(f'../data/{dataset_name}.json'))
            all_raw_base = raw_data_file['all_raw_base']
            all_raw_a = raw_data_file['all_raw_a']
            all_raw_b = raw_data_file['all_raw_b']
            all_raw_res = raw_data_file['all_raw_res']
            chunk_ids = chunk_identifiers(raw_data_file)

            self.process_data(all_raw_base, all_raw_a, all_raw_b, all_raw_res, partition_name, dataset_name, chunk_ids)
        self.data = pickle.load(open(data_path, "rb"))


    def process_data(self, all_raw_base, all_raw_a, all_raw_b, all_raw_res,  partition_name="train", dataset_name="dataset1", chunk_ids=None):
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
        train_index, valid_index, test_index = partitions(dataset_name, all_raw_a, chunk_ids)

        aux_files_path = f'AUX_FILES/{dataset_name}'
        if not os.path.exists(aux_files_path):
            os.makedirs(aux_files_path, exist_ok=True)

        all_index = {'train':train_index, 'valid': valid_index, 'test': test_index}
        json.dump(all_index, open(f'{aux_files_path}/all_index_{dataset_name}','w'))
        
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




