# Adaptive Video Streaming Over Wireless Networks

# Platform info
Requirements -
Python2/3, linux OS, node, npm

Following packages/libraries should be installed -
tensor-flow -
sudo apt-get -y install python-pip python-dev
sudo pip install tensorflow

tflearn -
sudo pip install tflearn
sudo apt-get -y install python-h5py
sudo apt-get -y install python-scipy

matplot lib -
sudo apt-get -y install python-matplotlib

# Steps to run
Have two linux systems(either VM or physical machines). One acts as server and another as client.

Server config -
1. Start ther node server using - noder server.js. Make sure sever.js is under ~/ path.
2. Verify that manifest.mpd is present under ~/static/ path.
3. Make sure all the video chunks of each rep lives under ~/static/<videoDIR>/
Video files can be downloaded from -  https://github.com/hongzimao/pensieve/tree/master/video_server

Client -
To run the client, use the staticdownloader.py. It takes the following args -
./staticdownloader.py [options] mpdURL [dstDir]

options - specifies the abr algo and verbosity.
mpdURL - the url path where the mpd file is hosted at server. Eg. http://10.128.0.33:5000/manifest.mpd.
dstDir - optional destination directory where the video chunks get downloaded. By default it is, ./download/.

Eg. -
To run Simple ABR -
./staticdownloader.py -v --abr http://10.128.0.33:5000/manifest.mpd

To run BOLA -
./staticdownloader.py -v --bola http://10.128.0.33:5000/manifest.mpd

To run BBA0 -
./staticdownloader.py -v --bba0 http://10.128.0.33:5000/manifest.mpd

To run BBA2 - 
./staticdownloader.py -v --bba2 http://10.128.0.33:5000/manifest.mpd

To run Pensieve - 
./staticdownloader.py -v --pensieve http://10.128.0.33:5000/manifest.mpd

Output -
On stdout, the time and the video chunk getting downloaded should be displayed.
At the end, various QoE metrics would be displayed.
Total play time - Total time video was being played by the video player
Total played utility - Total utility(log(bitrate)) of all the video chunks.
Avg played bitrate - Average of all the bitrates of the downloaded chunks.
Rebuffer time - Total rebuffer time observed.
Rebuffer count - Total rebuffer count(buffer was empty).
Next two lines contain two list values that can be copied to plots/plot1.py to generate the graph of comparing all the algos.
Next four lines specifies the utility values that can be used to generate the plots mentioned in plots/ path.
plot_average_qoe.py, plot_bitrate.py, plot_rebuffer_penalty.py, plot_smooth.py

# Code navigation
staticdownloader.py - client code
videoplayer.py - videoplayer code
server/server.js - server code
server/simulate_nw_trace.py - program to simulate network using trace file
server/3G_trace.json - 3G network trace file
server/static/manifest.mpd - MPD file of 6 reps. Video segments can be found here- https://github.com/hongzimao/pensieve/tree/master/video_server
plots/*.py - Plot graphs code
trigger_bandwidth_changer.sh - Script to trigger simulate_nw_trace.py on the remote server. Change the IP here as per your requirements. 

