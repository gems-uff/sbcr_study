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
    /usr/bin/time -o $LOGS_DIR/dataset1_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset1 "5,15,10" rq1_dataset1 2>&1 | tee $LOGS_DIR/dataset1_evaluation_process.txt
    echo "Evaluating for Java..."
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_Java_combination "5,10,20" rq1_Java 2>&1 | tee $LOGS_DIR/dataset2_Java_evaluation_process.txt
    echo "Evaluating for CSharp..."
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_CSharp_combination "3,10,40" rq2_CSharp 2>&1 | tee $LOGS_DIR/dataset2_CSharp_evaluation_process.txt
    echo "Evaluating for JavaScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_JavaScript_combination "9,15,20" rq2_JavaScript 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_evaluation_process.txt
    echo "Evaluating for TypeScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_TypeScript_combination "9,15,10" rq2_TypeScript 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_evaluation_process.txt
    echo "Evaluating for dataset1 rq3..."
    /usr/bin/time -o $LOGS_DIR/dataset1_rq3_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset1 "5,10,20" rq3_dataset1 2>&1 | tee $LOGS_DIR/dataset1_rq3_evaluation_process.txt
    echo "Evaluating for Dataset2 Java rq3..."
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_rq3_evaluation_time.txt -f "%E" python3 sbcr_evaluate.py dataset2_Java_combination "5,15,10" rq3_Java 2>&1 | tee $LOGS_DIR/dataset2_Java_rq3_evaluation_process.txt
} | tee -a $LOGS_DIR/all_sbcr_evaluation_typescript.txt


echo "All sbcr evaluation tasks completed."