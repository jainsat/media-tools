#!/bin/bash

set -ex

serverIP="10.128.0.33"

#ssh -i ~/.ssh/id_rsa "$serverIP" "sh -c '/home/rksinha_cs_stonybrook_edu/bandwidth_simulator'"
ssh -i ~/.ssh/id_rsa "$serverIP" "sh -c 'python /home/rksinha_cs_stonybrook_edu/abr-server/simulate_nw_trace.py &'"
#ssh -i ~/.ssh/id_rsa "$serverIP" "sh -c 'date'"
