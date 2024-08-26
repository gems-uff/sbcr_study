import os
import json
import pandas as pd

'''
    Cleans the chunk resolution text by removing potential context lines.
    We assume that 3 context lines are used before and after the conflicting chunk
    If the solution's context is different from the chunk's context, returns None
'''
def get_clean_solution(solution, before_context, after_context):
    solution = normalize_lines(solution.splitlines()).copy()
    before_context = normalize_lines(before_context.splitlines())
    after_context = normalize_lines(after_context.splitlines())
    
    if len(solution) >= 6:
        # what is the last line from the three first solution lines that is present in the before_context?
        solution_before_context_candidate = solution[:3]
        last_line_before_context = 0
        for index, line in enumerate(solution_before_context_candidate):
            if line in before_context:
                last_line_before_context = index
        
        # what is the first line from the last three solution lines that is present in the after_context?
        solution_after_context_candidate = solution[-3:]
        first_line_after_context = len(solution)
        for index, line in enumerate(solution_after_context_candidate):
            if line in after_context:
                first_line_after_context = len(solution) - (3 - index)
                break
        solution_before_context = solution[:last_line_before_context+1]
        solution_after_context = solution[first_line_after_context:]
        if (equivalent_context(solution_before_context, before_context) 
            and equivalent_context(solution_after_context, after_context)):
            return solution[last_line_before_context+1:first_line_after_context]
        else:
            return None
    return solution

def normalize_line(line):
    return line

def normalize_lines(lines):
    normalized_lines = []
    for line in lines:
            normalized_lines.append(normalize_line(line))
    return normalized_lines

def equivalent_context(context_solution, context_chunk):
    context_solution = remove_empty_lines(context_solution)
    context_chunk = remove_empty_lines(context_chunk)
    if len(context_solution) != len(context_chunk):
        return False
    for i in range(len(context_solution)):
        if context_solution[i] != context_chunk[i]:
            return False
    return True

def remove_empty_lines(lines):
    cleaned_lines = []
    for line in lines:
        if line != '':
            cleaned_lines.append(line)
    return cleaned_lines




if __name__ == "__main__":
    columns = ['all_raw_base', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'chunk_id']
    new_data = []
    data = pd.read_json('data/sbes2022_data.json')
    for index, row in data.iterrows():
        new_solution = get_clean_solution(row['solution'], row['before_context'], row['after_context'])
        if new_solution != None:
            new_data.append([row['base'], row['v1'], row['v2'], '\n'.join(new_solution), row['chunk_id']])
            
    # process solution to remove context lines
    json_data = pd.DataFrame(new_data, columns=columns).to_dict(orient="list")
    with open("data/dataset1_complete.json", "w") as json_file:
        json.dump(json_data, json_file, indent=4)