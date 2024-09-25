import pandas as pd

datasets=['dataset1', 'dataset2_Java_combination', 'dataset2_CSharp_combination', 'dataset2_JavaScript_combination', 'dataset2_TypeScript_combination']
data = []
for dataset in datasets:
    df = pd.read_excel(f'RESULTS/results_tunning_{dataset}_seed-3022024.xlsx', engine='openpyxl')
    df = pd.concat([df,pd.read_excel(f'tunning_v6_200_chunks_part1/RESULTS/results_tunning_{dataset}_seed-3022024.xlsx', engine='openpyxl')])
    df = df.dropna()
    df['configuration'] = list(zip(df['maximum_neighbors'], df['max_iterations_without_improvement'], df['ils_timeout']))
    for configuration in list(df['configuration'].unique()):
        data.append([dataset, configuration])
pd.DataFrame(data, columns=['dataset','configuration']).to_csv('collected_configurations.csv', index=False)