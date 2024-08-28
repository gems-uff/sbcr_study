import json
import math
import time
import subprocess
import sys 
if __name__ == '__main__':
    dataset_name = sys.argv[1]
    file_name = sys.argv[2]

    raw_data_file = json.load(open(f'../data/{dataset_name}_complete.json'))
    all_raw_base = raw_data_file['all_raw_base']

    all_num = len(all_raw_base)
#     print(all_num)
    jobs = []
    max_num = 30
    each_num = 1000
    for i in range(math.ceil(all_num / each_num)):
        while True:
            run_num = 0 
            for x in jobs:
                if x.poll() is None:
                    run_num += 1
            if run_num < max_num:
                break
            time.sleep(1)
        start = i * each_num
        end = min((i + 1) * each_num, all_num)
        p = subprocess.Popen("python %s %s %s %s"%(file_name, dataset_name, start, end), shell=True)
        jobs.append(p)
        time.sleep(1)
    for job in jobs:
        job.wait()