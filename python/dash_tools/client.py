#!/usr/bin/env python
"""Download and parse live DASH MPD and time download corresponding media segments.

Downloads all representations in the manifest. Only works for manifest with $Number$-template.
"""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2016, Dash Industry Forum.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#  * Redistributions of source code must retain the above copyright notice, this
#  list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation and/or
#  other materials provided with the distribution.
#  * Neither the name of Dash Industry Forum nor the names of its
#  contributors may be used to endorse or promote products derived from this software
#  without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS AS IS AND ANY
#  EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#  IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
#  INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#  NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
#  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.

import os
import staticmpdparser
import common
from threading import Lock

CREATE_DIRS = True
import pdb


'''
Config defines the configuration that any ABR algo takes before processing.
Right now, it takes 'fetches'.
prepare will set the bitrates in ascending order, using the 'bandwidth' from mpd file.
'''
class Config:
    def __init__(self, mpd, base_url=None, verbose=False):
        # Can house more parameters if needed
        self.mpd = mpd
        self.base_url = base_url
        self.verbose = verbose
        self.reps = None
        if mpd.type != "static":
            print "Can only handle static MPDs."
            sys.exit(1)
        self.prepare()


    def prepare(self):
        "Prepare by gathering info for each representation to download."
        reps = []
        print "Fetcher prepare phase"

        # We assume only one adaption set here (for video).
        adaptation_set = self.mpd.periods[0].adaptation_sets[0]
        if self.verbose:
            print adaptation_set
        for rep in adaptation_set.representations:
            init = adaptation_set.segment_template.initialization
            media = rep.segment_template.media
            rep_data = {'init' : init, 'media' : media,
                        'duration' : rep.segment_template.duration,
                        'timescale' : rep.segment_template.timescale,
                        'dur_s' : (rep.segment_template.duration * 1.0 /
                                   rep.segment_template.timescale),
                        'startNr' : rep.segment_template.startNumber,
                        'periodDuration' : int(self.mpd.periods[0].duration),
                        'base_url' : self.base_url,
                        'bandwidth': rep.bandwidth,
                        'height': rep.height,
                        'id' : rep.id}
            reps.append(rep_data)
        self.reps = reps

    # Returns the index in the self.fetch of the lowest bandwidth
    def getLowestBitRateIndex(self):
        min_val = self.reps[0]['bandwidth']
        index = 0
        for i, f in enumerate(self.reps):
            if f['bandwidth'] < min_val:
                min_val = f['bandwidth']
                index = i
        return index

'''
Download all the representations.
'''
class SimpleClient:
    def __init__(self, mpd, base_url, base_dst):
        # config can be the mpd file
        self.config = Config(mpd, base_url);
        self.file_writer = common.FileWriter(base_dst)

    def download(self):
        for rep in self.config.reps:
            init_url = os.path.join(rep['base_url'], rep['init'])
            data, _, _ = common.fetch_file(init_url)
            self.file_writer.write_file(rep['init'], data)
            thread = common.FetchThread("SegmentFetcher_%s" % rep['id'], rep, self.file_writer)
            thread.start()

'''
Abr class implements a basic ABR algo. init needs config which is of type Config
quality_from_throughput is called with last observed tput value.
'''
class AbrClient:
    def __init__(self, mpd, base_url, base_dst):
        # config can be the mpd file
        self.config = Config(mpd, base_url);
        self.quality_rep_map = {}
        self.file_writer = common.FileWriter(base_dst)
        for rep in self.config.reps:
            self.quality_rep_map[rep['bandwidth']] = rep

    def quality_from_throughput(self, tput):
        # in seconds
        segment_time = self.config.reps[0]['dur_s']

        quality = 0
        bitrates = self.quality_rep_map.keys()
        bitrates.sort()
        while (quality + 1 < len(bitrates) and ((segment_time * bitrates[quality + 1])/tput) <= segment_time):
            #latency + p * manifest.bitrates[quality + 1] / tput <= p):
            quality += 1
        return bitrates[quality]

    def download(self):
        throughput = 0

        # Start initially with the lowest quality
        # 1. Find the lowest bit rate representation id
        lowQualIndex = self.config.getLowestBitRateIndex()

        # 2. Download the init segment in lowest quality.
        fetchObj = self.config.reps[lowQualIndex]
        init_url = os.path.join(fetchObj['base_url'], fetchObj['init'])
        data, duration, size = common.fetch_file(init_url)
        print 'Using bitrate ', self.config.reps[lowQualIndex]['bandwidth'], ' for initial segment'
        self.file_writer.write_file(fetchObj['init'], data)

        # 3. Re-calculate throughput and measure latency.
        throughput = size/duration

        cur_seg = 0
        total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
        fetcher = common.Fetcher(self.file_writer)
        # Using index 0 - ASSUMPTION - all representation set have same duration and same start number
        # Note - we do not need threads until there are multiple adaptation sets i.e. audio and video separate adaptation sets.
        while cur_seg < total_segments:
            number = self.config.reps[0]['startNr'] + cur_seg

            # Call Abr(throughput). It returns the highest quality id that can be fetched.
            quality = self.quality_from_throughput(throughput)
            print 'Using bitrate ', quality, 'for segment', cur_seg, 'based on throughput ', throughput

            # Use the quality as index to fetch the media
            # quality directly corresponds to the index in self.fetches
            duration, size = fetcher.fetch(self.quality_rep_map[quality], number)
            # Recalculate throughput
            throughput = size/duration
            cur_seg += 1

