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
    /usr/bin/time -o $LOGS_DIR/dataset1_test_time.txt -f "%E" python3 run_mergegen.py dataset1 test 2>&1 | tee $LOGS_DIR/dataset1_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_test_time.txt -f "%E" python3 run_mergegen.py dataset2 test 2>&1 | tee $LOGS_DIR/dataset2_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_test_time.txt -f "%E" python3 run_mergegen.py dataset2_Java test 2>&1 | tee $LOGS_DIR/dataset2_Java_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_test_time.txt -f "%E" python3 run_mergegen.py dataset2_CSharp test 2>&1 | tee $LOGS_DIR/dataset2_CSharp_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_test_time.txt -f "%E" python3 run_mergegen.py dataset2_JavaScript test 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_test_time.txt -f "%E" python3 run_mergegen.py dataset2_TypeScript test 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_test_process.txt
} | tee -a $LOGS_DIR/all_testing_same_datasetmodel.txt

# Time each command and log the time taken
{
    /usr/bin/time -o $LOGS_DIR/dataset1_model2_test_time.txt -f "%E" python3 run_mergegen.py dataset1 test dataset2_Java 2>&1 | tee $LOGS_DIR/dataset1_model2_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_model1_test_time.txt -f "%E" python3 run_mergegen.py dataset2 test dataset1 2>&1 | tee $LOGS_DIR/dataset2_model1_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset1_model2_Java_test_time.txt -f "%E" python3 run_mergegen.py dataset1 test dataset2_Java 2>&1 | tee $LOGS_DIR/dataset1_model2_Java_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_model1_test_time.txt -f "%E" python3 run_mergegen.py dataset2_Java test dataset1 2>&1 | tee $LOGS_DIR/dataset2_Java_model1_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_model1_test_time.txt -f "%E" python3 run_mergegen.py dataset2_CSharp test dataset1 2>&1 | tee $LOGS_DIR/dataset2_CSharp_model1_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_model1_test_time.txt -f "%E" python3 run_mergegen.py dataset2_JavaScript test dataset1 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_model1_test_process.txt
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_model1_test_time.txt -f "%E" python3 run_mergegen.py dataset2_TypeScript test dataset1 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_model1_test_process.txt
} | tee -a $LOGS_DIR/all_testing_opposite_datasetmodel_3.txt

echo "All testing tasks completed."