import os
import json
import time

with open('/home/rksinha_cs_stonybrook_edu/abr-server/3G_trace.json') as json_file:
#with open('/home/rksinha_cs_stonybrook_edu/abr-server/trace1.json') as json_file:
	data = json.load(json_file)
	for line in data:
		cmd = "sudo tc qdisc replace dev ens4 root tbf rate {bw}kbit burst 32kbit  latency {latency}ms".format(bw=int(line["bandwidth_kbps"]), latency=line["latency_ms"])
		#print cmd
		os.system(cmd)
		time.sleep(int(line["duration_ms"]) / 1000)
