# Adaptive Video Streaming Over Wireless Networks

# Platform info
Requirements -
Python2/3, linux OS, node, npm <br/>

Following packages/libraries should be installed - <br/>
tensor-flow:<br/>
sudo apt-get -y install python-pip python-dev; sudo pip install tensorflow <br/>

tflearn:<br/>
sudo pip install tflearn ; sudo apt-get -y install python-h5py ; sudo apt-get -y install python-scipy <br/>

matplot lib:
sudo apt-get -y install python-matplotlib

# Steps to run
Have two linux systems(either VM or physical machines). One acts as server and another as client. <br/>

Server config -
1. Start ther node server using - noder server.js. Make sure sever.js is under ~/ path.
2. Verify that manifest.mpd is present under ~/static/ path.
3. Make sure all the video chunks of each rep lives under ~/static/<videoDIR>/
Video files can be downloaded from -  https://github.com/hongzimao/pensieve/tree/master/video_server

Client - <br/>
To run the client, use the staticdownloader.py. It takes the following args -<br/>
__./staticdownloader.py [options] mpdURL [dstDir]__.<br/>

options - specifies the abr algo and verbosity. <br/>
mpdURL - the url path where the mpd file is hosted at server. Eg. http://10.128.0.33:5000/manifest.mpd. <br/>
dstDir - optional destination directory where the video chunks get downloaded. By default it is, ./download/. <br/>

Eg. - <br/>
To run Simple ABR - <br/>
./staticdownloader.py -v --abr http://10.128.0.33:5000/manifest.mpd <br/>

To run BOLA - <br/>
./staticdownloader.py -v --bola http://10.128.0.33:5000/manifest.mpd <br/>

To run BBA0 - <br/>
./staticdownloader.py -v --bba0 http://10.128.0.33:5000/manifest.mpd <br/>

To run BBA2 -  <br/>
./staticdownloader.py -v --bba2 http://10.128.0.33:5000/manifest.mpd <br/>

To run Pensieve -  <br/>
./staticdownloader.py -v --pensieve http://10.128.0.33:5000/manifest.mpd <br/>

Output - <br/>
On stdout, the time and the video chunk getting downloaded should be displayed. <br/>
At the end, various QoE metrics would be displayed.<br/>
Total play time - Total time video was being played by the video player<br/>
Total played utility - Total utility(log(bitrate)) of all the video chunks.<br/>
Avg played bitrate - Average of all the bitrates of the downloaded chunks.<br/>
Rebuffer time - Total rebuffer time observed.<br/>
Rebuffer count - Total rebuffer count(buffer was empty).<br/>
Next two lines contain two list values that can be copied to plots/plot1.py to generate the graph of comparing all the algos.<br/>
Next four lines specifies the utility values that can be used to generate the plots mentioned in plots/ path.<br/>
plot_average_qoe.py, plot_bitrate.py, plot_rebuffer_penalty.py, plot_smooth.py<br/>

# MPD file
```xml
<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:mpeg:dash:schema:mpd:2011" xmlns:scte35="http://www.scte.org/schemas/35/2014SCTE35.xsd" xsi:schemaLocation="urn:mpeg:dash:schema:mpd:2011 DASH-MPD.xsd" profiles="urn:mpeg:dash:profile:isoff-live:2011" type="static" minBufferTime="PT5.000S" maxSegmentDuration="PT2.005S" availabilityStartTime="2016-01-20T21:10:02Z" mediaPresentationDuration="PT193.680S">
    <Period id="period0" duration="PT193.680S">
        <AdaptationSet mimeType="video/mp4" segmentAlignment="true" startWithSAP="1" maxWidth="1920" maxHeight="1080" maxFrameRate="30000/1001" par="1:1">
            <SegmentTemplate timescale="90000" initialization="$RepresentationID$/Header.m4s" media="$RepresentationID$/$Number$.m4s" startNumber="1" duration="359408" presentationTimeOffset="0" />
            <Representation id="video1" bandwidth="4300000" codecs="avc1.4D401E" width="1920" height="1080" frameRate="30000/1001" sar="1:1" scanType="progressive" />
            <Representation id="video2" bandwidth="2850000" codecs="avc1.4D401E" width="1280" height="720" frameRate="30000/1001" sar="1:1" scanType="progressive" />
            <Representation id="video3" bandwidth="1850000" codecs="avc1.4D401E" width="1024" height="576" frameRate="30000/1001" sar="1:1" scanType="progressive" />
            <Representation id="video4" bandwidth="1200000" codecs="avc1.4D401E" width="768" height="432" frameRate="30000/1001" sar="1:1" scanType="progressive" />
            <Representation id="video5" bandwidth="750000" codecs="avc1.4D401E" width="640" height="360" frameRate="30000/1001" sar="1:1" scanType="progressive" />
            <Representation id="video6" bandwidth="300000" codecs="avc1.4D401E" width="320" height="180" frameRate="30000/1001" sar="1:1" scanType="progressive" />
        </AdaptationSet>
    </Period>
</MPD>
```

# Code navigation
staticdownloader.py - client code <br/>
videoplayer.py - videoplayer code <br/>
server/server.js - server code <br/>
server/simulate_nw_trace.py - program to simulate network using trace file <br/>
server/3G_trace.json - 3G network trace file <br/>
server/static/manifest.mpd - MPD file of 6 reps. Video segments can be found here- https://github.com/hongzimao/pensieve/tree/master/video_server <br/>
plots/*.py - Plot graphs code <br/>
trigger_bandwidth_changer.sh - Script to trigger simulate_nw_trace.py on the remote server. Change the IP here as per your requirements. <br/>

Thanks to @mdasari823 for mentoring.
