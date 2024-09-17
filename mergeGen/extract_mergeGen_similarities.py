import pylcs
import os
import pandas as pd
import sys
'''
Script para calcular a similaridade dos candidatos gerados pelo MergeGen com a solução (usando LCS)

Dada uma pasta (a pasta onde estão as saidas do MergeGen. Normalmente fica na pasta OUTPUT/nome_modelo/test_OUTPUT):
    Acessar a pasta FAIL
        Para cada arquivo dessa pasta:
            Abrir o arquivo
                Separar o candidato gerado pelo MergeGen (primeiro elemento da lista que vem depois de output:)
                A referencia (vem depois de ref_dataloader:)
                O tempo (vem depois de time:)
            Salvar os dados coletados do arquivo
    Acessar a pasta SUCCEED
        Para cada arquivo dessa pasta:
            repetir o processo dos arquivos em FAIL

Arquivo de exemplo:
ref_dataloader:
fillRepairReadsValues(nodeValues, key, node, fetched); failureDetector.recordSuccess(node);
---------------------------------
output:
['if(repairReads) { for(Versioned<byte[]> f: fetched) nodeValues.add(new NodeValue<ByteArray, byte[]>(node.getId(), key, f)); } failureDetector.recordSuccess(node);', 'failureDetector.recordSuccess(node);', 'if(repairReads) { for(Versioned<byte[]> f: fetched) nodeValues.add(new NodeValue<ByteArray, byte[]>(node.getId(), key, f)); } failureDetector.recordFailure(node);']
---------------------------------
time: 0.349259 s

'''
def extract_data(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            reference = lines[1].strip()
            output = eval(lines[4].strip())[0]
            time = float(lines[6].split(' ')[1])
    except:
        print('Error reading file: ', file_path)
        return None, None, None
    return output, reference, time

def analyze_folder(folder_path, max_resolve_length):
    if max_resolve_length is not None:
        max_resolve_length = int(max_resolve_length)
    
    files = os.listdir(folder_path)
    outputs = []
    references = []
    times = []
    chunk_indexes = []
    for file in files:
        output, reference, time = extract_data(folder_path + '/' + file)
        if output is not None:
            if max_resolve_length is not None:
                outputs.append(output[:max_resolve_length])
                references.append(reference[:max_resolve_length])
            else:
                outputs.append(output)
                references.append(reference)
            times.append(time)
            chunk_indexes.append(file)
    return outputs, references, times, chunk_indexes

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

def calculate_similarity(output, reference):
    return get_gestalt(output, reference)

def main(model, dataset, max_resolve_length):
    path = 'OUTPUT/' + dataset + '/model_' + model + '/test_OUTPUT'
    fail_path = path + '/FAIL'
    succeed_path = path + '/SUCCEED'
    fail_outputs, fail_references, fail_times, fail_chunk_indexes = analyze_folder(fail_path, max_resolve_length)
    succeed_outputs, succeed_references, succeed_times, succeed_chunk_indexes = analyze_folder(succeed_path, max_resolve_length)
    fail_similarities = []
    succeed_similarities = []
    for i in range(len(fail_outputs)):
        fail_similarities.append(calculate_similarity(fail_outputs[i], fail_references[i]))
    for i in range(len(succeed_outputs)):
        succeed_similarities.append(calculate_similarity(succeed_outputs[i], succeed_references[i]))
    data = []
    for i in range(len(fail_outputs)):
        data.append((fail_chunk_indexes[i], fail_similarities[i], fail_times[i], 'FAIL'))
    for i in range(len(succeed_outputs)):
        data.append((succeed_chunk_indexes[i], succeed_similarities[i], succeed_times[i], 'SUCCEED'))
    pd.DataFrame(data, columns=['chunk_index', 'similarity', 'time', 'result']).to_csv(f'RESULTS/mergeGen_{dataset}_model_{model}_similarities.csv', index=False)
    # print('Fail similarities:', fail_similarities)
    # print('Succeed similarities:', succeed_similarities)
dataset_name = sys.argv[1]
model_name = sys.argv[2]
if len(sys.argv) > 3:
    max_resolve_length = sys.argv[3]
else:
    max_resolve_length = None
main(model_name, dataset_name, max_resolve_length)