#!/bin/bash

LOGS_DIR="LOGS"
cd mergeGen

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory..."
    mkdir $LOGS_DIR
fi

# Time each command and log the time taken
{
    # /usr/bin/time -o $LOGS_DIR/dataset1_train_time.txt -f "%E" python3 run_mergegen.py dataset1 train 2>&1 | tee $LOGS_DIR/dataset1_train_process.txt
    # /usr/bin/time -o $LOGS_DIR/dataset2_train_time.txt -f "%E" python3 run_mergegen.py dataset2 train 2>&1 | tee $LOGS_DIR/dataset2_train_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_train_time.txt -f "%E" python3 run_mergegen.py dataset2_Java train 2>&1 | tee $LOGS_DIR/dataset2_Java_train_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_train_time.txt -f "%E" python3 run_mergegen.py dataset2_CSharp train 2>&1 | tee $LOGS_DIR/dataset2_CSharp_train_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_train_time.txt -f "%E" python3 run_mergegen.py dataset2_JavaScript train 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_train_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_train_time.txt -f "%E" python3 run_mergegen.py dataset2_TypeScript train 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_train_process.txt
} | tee -a $LOGS_DIR/all_training.txt

echo "All training tasks completed."