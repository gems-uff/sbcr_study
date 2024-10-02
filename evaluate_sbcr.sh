#!/bin/bash

LOGS_DIR="LOGS"
cd sbcr

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory"
    mkdir $LOGS_DIR
fi

# Time each command and log the time taken
{
    echo "Evaluating for dataset1..."
    /usr/bin/time -o $LOGS_DIR/dataset1_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset1 "3,15,40" 2>&1 | tee $LOGS_DIR/dataset1_evaluation_process.txt
    echo "Evaluating for Java..."
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_Java_combination "3,20,10" 2>&1 | tee $LOGS_DIR/dataset2_Java_evaluation_process.txt
    echo "Evaluating for CSharp..."
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_CSharp_combination "9,5,10" 2>&1 | tee $LOGS_DIR/dataset2_CSharp_evaluation_process.txt
    echo "Evaluating for JavaScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_JavaScript_combination "7,10,40" 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_evaluation_process.txt
    echo "Evaluating for TypeScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_TypeScript_combination "3,10,10" 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_evaluation_process.txt
} | tee -a $LOGS_DIR/all_sbcr_evaluation.txt


echo "All sbcr evaluation tasks completed."