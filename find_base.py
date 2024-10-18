import pandas as pd

def encontrar_conteudo_regiao_conflito_incremental(conteudo_base, upper_context, lower_context):
    upper_lines = upper_context.splitlines(keepends=True)
    lower_lines = lower_context.splitlines(keepends=True)

    for i in range(1, len(upper_lines)):
        upper_fragment = ''.join(upper_lines[-i:])
        posicoes_superiores = encontrar_ocorrencias(conteudo_base, upper_fragment)
        if len(posicoes_superiores) > 0:
            for j in range(1,len(lower_lines)+1):

                lower_fragment = ''.join(lower_lines[:j])
                posicoes_inferiores = encontrar_ocorrencias(conteudo_base, lower_fragment)
                count_possible_matches = 0
                last_pos_sup = None
                last_pos_inf = None
                for pos_sup in posicoes_superiores:
                    for pos_inf in posicoes_inferiores:
                        if pos_inf > pos_sup:
                            count_possible_matches +=1
                            last_pos_sup = pos_sup
                            last_pos_inf = pos_inf
                
                if count_possible_matches == 1:
                    linha_inicial = conteudo_base[:last_pos_sup + len(upper_fragment)].count('\n')
                    linha_final = conteudo_base[:last_pos_inf].count('\n')
                    conteudo_conflito = conteudo_base[last_pos_sup + len(upper_fragment):last_pos_inf]
                    return [linha_inicial, linha_final, conteudo_conflito]
    return []


def encontrar_ocorrencias(conteudo, fragmento):
    posicoes = []
    pos = conteudo.find(fragmento)
    while pos != -1:
        posicoes.append(pos)
        pos = conteudo.find(fragmento, pos + 1)
    return posicoes

file_name = 'base_extraction.json'
data = []
count = 1
df = pd.read_json('dataset1_with_context.json')
for index, row in df.iterrows():
    print(f' ({count}/{len(df)})Analyzing chunk: ', row['chunk_id'])
    if len(row['all_raw_a'])<20000 and len(row['all_raw_b']) < 20000:
        upper_context = row['before_context']
        lower_context = row['after_context']
        base_file = row['all_raw_base']
        conflict_regions = encontrar_conteudo_regiao_conflito_incremental(base_file, upper_context, lower_context)
        if len(conflict_regions) > 0:
            line_start = conflict_regions[0]
            line_end = conflict_regions[1]
            content = ''.join(conflict_regions[2])
            data.append([row['chunk_id'], int(line_start), int(line_end), content])
        else:
            data.append([row['chunk_id'], '', '', ''])
    else:
            data.append([row['chunk_id'], '', '', ''])
    
    if count % 50 == 0:
        pd.DataFrame(data, columns=['chunk_id', 'line_start', 'line_end', 'content']).to_json(file_name, orient='records', lines=True)
    count+=1
    
pd.DataFrame(data, columns=['chunk_id', 'line_start', 'line_end', 'content']).to_json(file_name, orient='records', lines=True)
