#!/bin/bash

LOGS_DIR="LOGS"
cd sbcr

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory..."
    mkdir $LOGS_DIR
fi

# Time each command and log the time taken
{
    echo "Tunning for dataset1..."
    /usr/bin/time -o $LOGS_DIR/dataset1_tunning_time.txt -f "%E" python3 sbcr_tunning.py dataset1 2>&1 | tee $LOGS_DIR/dataset1_tunning_process.txt
    echo "Tunning for Java..."
    /usr/bin/time -o $LOGS_DIR/dataset2_Java_tunning_time.txt -f "%E" python3 sbcr_tunning.py dataset2_Java 2>&1 | tee $LOGS_DIR/dataset2_Java_tunning_process.txt
    echo "Tunning for CSharp..."
    /usr/bin/time -o $LOGS_DIR/dataset2_CSharp_tunning_time.txt -f "%E" python3 sbcr_tunning.py dataset2_CSharp 2>&1 | tee $LOGS_DIR/dataset2_CSharp_tunning_process.txt
    echo "Tunning for JavaScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_JavaScript_tunning_time.txt -f "%E" python3 sbcr_tunning.py dataset2_JavaScript 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_tunning_process.txt
    echo "Tunning for TypeScript..."
    /usr/bin/time -o $LOGS_DIR/dataset2_TypeScript_tunning_time.txt -f "%E" python3 sbcr_tunning.py dataset2_TypeScript 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_tunning_process.txt
} | tee -a $LOGS_DIR/all_sbcr_tunning.txt


echo "All sbcr tunning tasks completed."