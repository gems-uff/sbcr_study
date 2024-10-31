#!/bin/bash

LOGS_DIR="LOGS"

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory"
    mkdir $LOGS_DIR
fi


{
python3 collect_dataset_stats.py dataset1_complete 2>&1 | tee $LOGS_DIR/dataset1_stats_collection.txt
python3 collect_dataset_stats.py dataset2_Java_complete 2>&1 | tee $LOGS_DIR/dataset2_Java_stats_collection.txt
python3 collect_dataset_stats.py dataset2_CSharp_complete 2>&1 | tee $LOGS_DIR/dataset2_CSharp_stats_collection.txt
python3 collect_dataset_stats.py dataset2_JavaScript_complete 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_stats_collection.txt
python3 collect_dataset_stats.py dataset2_TypeScript_complete 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_stats_collection.txt
} | tee -a $LOGS_DIR/datasets_stats_collection.txt

echo "All stats collected."