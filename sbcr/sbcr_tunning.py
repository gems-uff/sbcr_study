import pandas as pd
import random
import os
import subprocess
import time
import pylcs
from datetime import datetime
import sys

NEIGHBOR_FINDING_TIMEOUT_SECONDS = 3
LOCAL_SEARCH_TIMEOUT_SECONDS = 5
ILS_TIMEOUT_SECONDS = 100
ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT = 5
LOCAL_SEARCH_MAXIMUM_NEIGHBORS = 5
TUNNING_TIMEOUTS = [10,20,30]
MAX_ITERATIONS_WITHOUT_IMPROVEMENT_VALUES = [5,10,15]
LOCAL_SEARCH_MAXIMUM_NEIGHBORS_VALUES = [3,5,7]
DEBUG_FOLDER = "DEBUG"
RESULTS_FOLDER = "RESULTS"
OUTPUT_FOLDER = "OUTPUT"
DEBUG_ACTIVE = False
SAVE_ITERATION_INFO = True
RANDOM_SEED = 3022024
DATASET = "dataset1"

CANDIDATES_FOLDER = f"{OUTPUT_FOLDER}/candidates_tunning"
SAVE_CANDIDATE = False
NUMBER_OF_CHUNKS = 100

if len(sys.argv) > 1:
    DATASET = sys.argv[1]
    if len(sys.argv) > 2:
        NUMBER_OF_CHUNKS = int(sys.argv[2])

DEBUG_REPOSITORY_PATH = f"{DEBUG_FOLDER}/debug_timeout_{DATASET}"
ORIGINAL_DEBUG_REPOSITORY_PATH = DEBUG_REPOSITORY_PATH
        
if not os.path.exists(RESULTS_FOLDER):
    os.mkdir(RESULTS_FOLDER)
RESULT_FILE = f'{RESULTS_FOLDER}/results_tunning_{DATASET}_seed-{RANDOM_SEED}.xlsx'

random.seed(RANDOM_SEED)

if not os.path.exists(OUTPUT_FOLDER):
    os.mkdir(OUTPUT_FOLDER)
if DEBUG_ACTIVE:
    if not os.path.exists(DEBUG_FOLDER):
        os.mkdir(DEBUG_FOLDER)
if not os.path.exists("tmp"):
    os.mkdir("tmp")

def get_sorted_random_lines(original_list, n):
    # Get n random indices
    random_indices = random.sample(range(len(original_list)), n)

    # Sort the indices in ascending order
    sorted_indices = sorted(random_indices)

    # Create a new list using the sorted indices
    new_list = [original_list[i] for i in sorted_indices]

    return new_list
    
def partial_order_random_candidate(v1, v2):
    v1 = v1.splitlines()
    v2 = v2.splitlines()
    number_lines_v1 = random.randrange(len(v1)+1)
    number_lines_v2 = random.randrange(len(v2)+1)
    candidate_size = number_lines_v1 + number_lines_v2
    lines_v1 = random.sample(v1, number_lines_v1).sort()
    lines_v2 = random.sample(v2, number_lines_v2).sort()
    
    lines_v1 = get_sorted_random_lines(v1, number_lines_v1)
    lines_v2 = get_sorted_random_lines(v2, number_lines_v2)
    
    candidate = []
    while(len(candidate) < candidate_size):
        line_source = ''
        if(len(lines_v1)>0 and len(lines_v2)>0):
            line_source = random.choice(['v1', 'v2'])
        elif len(lines_v2)==0:
            line_source='v1'
        else:
            line_source='v2'
        if line_source == 'v1':
            candidate.append(lines_v1.pop(0))
        else:
            candidate.append(lines_v2.pop(0))
    
    return '\n'.join(candidate)

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

def get_lcs(text1,text2):
    res = pylcs.lcs_sequence_idx(text1, text2)
    lcs = ''.join([text2[i] for i in res if i != -1])
    return lcs

def get_gestalt(file1,file2):
    try:
        with open(file1, 'r', encoding='iso-8859-1') as f1:
            file1_text = f1.read()
        with open(file2, 'r', encoding='iso-8859-1') as f2:
            file2_text = f2.read()
            if file1_text == file2_text:
                return 1
            return 2*len(get_lcs(file1_text, file2_text)) / (len(file1_text) + len(file2_text))
    except Exception as e:
        print(e)
        return 0
    
def write_file(content, file_name):
    with open(file_name, 'w') as f:
        f.write(str(content))

def execute_command_timeout(command, timeout, print_output=False):
    try:
        print(f'{time.ctime()} ### Executing command: ', command, flush=True)
        result = subprocess.check_output([command], stderr=subprocess.STDOUT, text=True, shell=True, timeout=timeout)
        return result
    except subprocess.CalledProcessError as e:
        # print("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output), flush=True)
        return e.output

def save_candidate(candidate, name):
    if DEBUG_ACTIVE:
        write_file(candidate, f'{DEBUG_REPOSITORY_PATH}/{name}')

def save_iterations_info(iterations_info):
    if SAVE_ITERATION_INFO:
        if not os.path.exists(f'{DEBUG_REPOSITORY_PATH}/iterations_info.csv'):
            with open(f'{DEBUG_REPOSITORY_PATH}/iterations_info.csv', 'w') as f:
                f.write('LOCAL_SEARCH_MAXIMUM_NEIGHBORS,ILS_TIMEOUT_SECONDS,MAX_ITERATIONS_WITHOUT_IMPROVEMENT,iteration_number,fitness,elapsed_time,iterations_without_improvement\n')
        with open(f'{DEBUG_REPOSITORY_PATH}/iterations_info.csv', 'a') as f:
            for iteration_info in iterations_info:
                f.write(f'{LOCAL_SEARCH_MAXIMUM_NEIGHBORS},{ILS_TIMEOUT_SECONDS},{ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT},{iteration_info[0]},{iteration_info[1]},{iteration_info[2]},{iteration_info[3]}\n')

def clear_iteration_info():
    if SAVE_ITERATION_INFO:
        if os.path.exists(f'{DEBUG_REPOSITORY_PATH}'):
            for root, dirs, files in os.walk(f'{DEBUG_REPOSITORY_PATH}', topdown=False):
                for dir in dirs:
                    if os.path.exists(f'{DEBUG_REPOSITORY_PATH}/{dir}/iterations_info.csv'):
                        os.remove(f'{DEBUG_REPOSITORY_PATH}/{dir}/iterations_info.csv')


def get_current_timestamp():
    current_datetime = datetime.now()
    return current_datetime.strftime("%d-%m-%Y_%H-%M-%S-%f")

def evaluate(candidate, v1, v2):
    try:
        write_file(candidate, 'tmp/candidate')
        write_file(v1, 'tmp/v1')
        write_file(v2, 'tmp/v2')

        v1_similarity = get_gestalt('tmp/candidate', 'tmp/v1')
        v2_similarity = get_gestalt('tmp/candidate', 'tmp/v2')
        return (v1_similarity + v2_similarity) / 2
    except Exception as e:
        print(e)
        return -1

def compare(content1, content2):
    try:
        write_file(content1, 'tmp/content1')
        write_file(content2, 'tmp/content2')
        content_similarity = get_gestalt('tmp/content1', 'tmp/content2')
        
        return content_similarity
    except Exception as e:
        print(e)
        return -1

class LineOccurrence:
    def __init__(self, content) -> None:
        self.content = content
        self.last_v1_index = None
        self.last_v2_index = None
        self.v1 = False
        self.v2 = False

    def set_version(self, version):
        if version == 'v1':
            self.v1 = True
        if version == 'v2':
            self.v2 = True
    
    def set_index(self, version, index):
        if version == 'v1':
            if self.last_v1_index != None:
                if index > self.last_v1_index:
                    self.last_v1_index = index
            else:
                self.last_v1_index = index

        if version == 'v2':
            if self.last_v2_index != None:
                if index > self.last_v2_index:
                    self.last_v2_index = index
            else:
                self.last_v2_index = index

def populate_index(lines, version, index):
    for line_index, line in enumerate(lines):
        if line not in index:
            occurrence = LineOccurrence(line)
            occurrence.set_version(version)
            occurrence.set_index(version, line_index+1)
            index[line] = occurrence
        else:
            occurrence = index[line]
            occurrence.set_version(version)
            occurrence.set_index(version, line_index+1)
            index[line] = occurrence
    return index


def violates_partial_order(v1,v2, candidate):
    v1 = normalize_lines(v1.splitlines())
    v2 = normalize_lines(v2.splitlines())
    
    if type(candidate) == str:
        candidate = normalize_lines(candidate.splitlines())
    index = {}
    index = populate_index(v1, 'v1', index)
    index = populate_index(v2, 'v2', index)
    
    last_v1_index = None
    last_v2_index = None
    
    for line in candidate:
        if line != '':
            if line in index:
                # side, side_index, multiple = index[line]
                occurrence = index[line]
                if occurrence.v1:
                    if last_v1_index != None:
                        if occurrence.last_v1_index < last_v1_index:
                            return True
                    last_v1_index = occurrence.last_v1_index
                if occurrence.v2:
                    if last_v2_index != None:
                        if occurrence.last_v2_index < last_v2_index:
                            return True
                    last_v2_index = occurrence.last_v2_index
    return False

'''
    Gets one random line of available_lines and 
        adds it to the current_lines at the parameter position
'''
def add_line(current_lines, position, available_lines):
    current_lines.insert(position,random.choice(available_lines))

def get_available_lines(current_lines, all_possible_lines):
    available_lines = all_possible_lines.copy()
    for line in current_lines:
        available_lines.remove(line)
    return available_lines

'''
    Given a candidate, returns a random neighbor
        A neighbor is defined as a candidate that differs
        at most in one line (either by addition or removal)
'''
def get_random_neighbor(candidate, v1, v2):
    candidate_lines = candidate.splitlines()
    v1_lines = v1.splitlines()
    v2_lines = v2.splitlines()
    raffled_action = random.choice(['add', 'remove'])
    chunk_size = len(v1_lines) + len(v2_lines)

    if len(candidate_lines)>=chunk_size:
        raffled_action = 'remove'

    if len(candidate_lines) == 1:
        raffled_action = 'add'
    
    if len(candidate_lines) > 0:
        position = random.randint(0, len(candidate_lines)-1)
    else:
        position = 0
        raffled_action = 'add'
        
    if raffled_action == 'add':
        add_line(candidate_lines, position, get_available_lines(candidate_lines, v1_lines + v2_lines))
    else:
        candidate_lines.pop(position)
    return '\n'.join(candidate_lines)

'''
    Gets a random neighbor and 
        check if the neighbor satisfies the partial order,
        Otherwise, generate another, until one that satisfies is found
    Timeouts if no partial order complaint neighbor is found
'''
def get_next_neighbor(candidate, v1, v2, neighbors):
    random_neighbor = get_random_neighbor(candidate, v1, v2)
    start_time = time.time()
    while violates_partial_order(v1, v2, random_neighbor) or hash(random_neighbor) in neighbors:
        if time.time() - start_time > NEIGHBOR_FINDING_TIMEOUT_SECONDS:
            return None
        random_neighbor = get_random_neighbor(candidate, v1, v2)
    return random_neighbor

def get_fittest(neighbors):
    fittest_neighbor = None
    fittest_value = -9999999
    for neighbor in neighbors.items():
        if neighbor[1][1] > fittest_value:
            fittest_neighbor = neighbor[1][0]
            fittest_value = neighbor[1][1]
    return fittest_neighbor, fittest_value

def local_search(starting_candidate, starting_candidate_fitness, n, v1, v2, source, depth):
    neighbors = {}
    start_time = time.time()
    while len(neighbors) < n and time.time() - start_time < LOCAL_SEARCH_TIMEOUT_SECONDS:
        s_new = get_next_neighbor(starting_candidate, v1, v2, neighbors)
        if s_new != None:
            f_new = evaluate(s_new, v1, v2)
            neighbors[hash(s_new)] = [s_new, f_new]

            save_candidate(s_new, f'neighbor_{source}-{depth}_{get_current_timestamp()}')
            save_candidate(f_new, f'neighbor_{source}-{depth}_{get_current_timestamp()}_f')

    s_candidate, f_candidate = get_fittest(neighbors)
    if f_candidate > starting_candidate_fitness:
        return local_search(s_candidate, f_candidate, n, v1, v2, 'ls_in', depth+1)
    else:
        return starting_candidate, starting_candidate_fitness

def pertubate(candidate, v1, v2):
    return partial_order_random_candidate(v1, v2)

def ils_resolution(v1, v2):

    save_candidate(v1+'\n'+v2, 'available_lines')

    s_star = partial_order_random_candidate(v1, v2)
    f_star = evaluate(s_star, v1, v2)

    save_candidate(s_star, 'initial_candidate')
    save_candidate(f_star, 'initial_candidate_f')

    s_star, f_star = local_search(s_star, f_star, LOCAL_SEARCH_MAXIMUM_NEIGHBORS, v1, v2, 'initial', 0)

    save_candidate(s_star, 'initial_candidate_from_localsearch')
    save_candidate(f_star, 'initial_candidate_from_localsearch_f')

    start_time = time.time()
    iteration_number = 1
    iterations_without_improvement = 0
    iterations_info = []
    while (time.time() - start_time < ILS_TIMEOUT_SECONDS) and iterations_without_improvement <= ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT:
        s_new = pertubate(s_star, v1, v2)
        f_new = evaluate(s_new, v1, v2)

        save_candidate(s_new, f'perturbed_candidate_it-{iteration_number}')
        save_candidate(f_new, f'perturbed_candidate_it-{iteration_number}_f')
        save_candidate(time.time() - start_time, f'perturbed_candidate_it-{iteration_number}_t')

        s_star_new, f_star_new = local_search(s_new, f_new, LOCAL_SEARCH_MAXIMUM_NEIGHBORS, v1, v2, f'it-{iteration_number}', 0)

        save_candidate(s_star_new, f'candidate_after_localsearch_it-{iteration_number}')
        save_candidate(f_star_new, f'candidate_after_localsearch_it-{iteration_number}_f')
        save_candidate(time.time() - start_time, f'candidate_after_localsearch_it-{iteration_number}_t')
        original_iterations = iterations_without_improvement
        if f_star_new > f_star:
            s_star = s_star_new
            f_star = f_star_new
            iterations_without_improvement = 0
        else:
            iterations_without_improvement += 1
        iterations_info.append([iteration_number, f_star, time.time() - start_time, original_iterations])
        iteration_number+=1
    save_iterations_info(iterations_info)
    return s_star, f_star

def adapt_dataset(df):
    if 'chunk_id' not in df.columns:
        df['chunk_id'] = df['merge_id'].astype(str) + '-' + df['chunk_number'].astype(str)
    if 'v1' not in df.columns:
        df.rename(columns={'all_raw_a':'v1', 'all_raw_b':'v2', 'all_raw_res':'solution'}, inplace=True)
            

def tunning():
    global DEBUG_REPOSITORY_PATH, LOCAL_SEARCH_MAXIMUM_NEIGHBORS, ILS_TIMEOUT_SECONDS, ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT
    df_chunks = pd.read_json(f"../data/{DATASET}_training.json")
    df_chunks = df_chunks.sample(NUMBER_OF_CHUNKS, random_state=RANDOM_SEED)
    data = []
    adapt_dataset(df_chunks)
    clear_iteration_info()
    count = 1
    chunk_count = 1
    columns = ['chunk_id', 'fitness', 'solution_sim_lcs', 'status', 'neighbor_timeout', 'local_search_timeout', 'ils_timeout', 'maximum_neighbors', 'max_iterations_without_improvement', 'time_seconds']
    analyzed_chunk_ids = []
    if os.path.exists(RESULT_FILE):
        df = pd.read_excel(RESULT_FILE, engine='openpyxl')
        data = df.values.tolist()
        analyzed_chunk_ids = df['chunk_id'].unique()
    for index, row in df_chunks.iterrows():
        chunk_id = row['chunk_id']
        if chunk_id not in analyzed_chunk_ids:
            print(f"{time.ctime()} ### Analyzing chunk ({chunk_id}) {chunk_count} of {len(df_chunks)}", flush=True)
            if len(row['v1'])<20000 and len(row['v2']) < 20000:
                v1 = row['v1']
                v2 = row['v2']
                if 'before_context' in df_chunks.columns:
                    solution = get_clean_solution(row['solution'], row['before_context'], row['after_context'])
                else:
                    solution = row['solution']
                if solution != None:
                    solution = '\n'.join(solution)
                    try:
                        DEBUG_REPOSITORY_PATH = f"{ORIGINAL_DEBUG_REPOSITORY_PATH}/{chunk_id}"
                        if not os.path.exists(f"{DEBUG_REPOSITORY_PATH}"):
                            os.makedirs(DEBUG_REPOSITORY_PATH, exist_ok=True) 
                        for max_iterations_without_improvement in MAX_ITERATIONS_WITHOUT_IMPROVEMENT_VALUES:
                            ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT = max_iterations_without_improvement
                            for maximum_neighbors in LOCAL_SEARCH_MAXIMUM_NEIGHBORS_VALUES:
                                LOCAL_SEARCH_MAXIMUM_NEIGHBORS = maximum_neighbors
                                for timeout in TUNNING_TIMEOUTS:
                                    ILS_TIMEOUT_SECONDS = timeout
#                                     print(f"Analyzing chunk ({chunk_id}) with {ILS_TIMEOUT_SECONDS}s timeout, {LOCAL_SEARCH_MAXIMUM_NEIGHBORS} maximum neighbors, {ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT} max iterations without improvement", flush=True)
                                    start_time = time.time()
                                    candidate, fitness = ils_resolution(v1, v2)
                                    end_time = time.time()
                                    elapsed_time = end_time - start_time
                                    if SAVE_CANDIDATE:
                                        if not os.path.exists(f"{OUTPUT_FOLDER}"):
                                            os.mkdir(OUTPUT_FOLDER)
                                        write_file(candidate, f"{OUTPUT_FOLDER}/{chunk_id}")
                                    lcs_solution_similarity = compare(solution, candidate)
#                                     print(f"Elapsed time: {elapsed_time}, Fitness: {fitness}, LCS Similarity: {lcs_solution_similarity}", flush=True)
                                    data.append([row['chunk_id'], fitness, lcs_solution_similarity, 'ok', NEIGHBOR_FINDING_TIMEOUT_SECONDS, LOCAL_SEARCH_TIMEOUT_SECONDS, ILS_TIMEOUT_SECONDS, LOCAL_SEARCH_MAXIMUM_NEIGHBORS, ILS_STOP_CRITERIA_ITERATIONS_WITHOUT_IMPROVEMENT, elapsed_time])
                                    if count % 5 == 0:
                                        pd.DataFrame(data, columns=columns).to_excel(RESULT_FILE, index=False)
                                        count=0
                                    count+=1
                    except Exception as e:
                        error = e
                        print(e)
                        data.append([row['chunk_id'], "", "", e, "", "", "", "", "", ""])
                else:
                    print('Empty solution', flush=True)
            else:
                print(len(row['v1']))
                print(len(row['v2']))
                data.append([row['chunk_id'], "", "", "OUT_OF_LIMITS", "", "", "", "", "", ""])
        else:
            print(f"Chunk ({chunk_id}) {count} of {len(df_chunks)} was already analyzed before.", flush=True)
        chunk_count+=1
    pd.DataFrame(data, columns=columns).to_excel(RESULT_FILE, index=False)
tunning()