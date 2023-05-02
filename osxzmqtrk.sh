#!/bin/bash
export HOME=/Users/ccoupe/
export USER=ccoupe
source /Users/ccoupe/.bash_profile
conda activate py38
cd /usr/local/lib/zmqtracker
python3 zmq_tracker.py -c mini.json
