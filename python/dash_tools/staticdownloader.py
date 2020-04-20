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
import sys
import time
from threading import Thread, Lock
import signal
import urllib2
import urlparse
import staticmpdparser

CREATE_DIRS = True


class FileWriter(object):
    "File writer that handles standard file system."

    def __init__(self, base_dst, verbose=False):
        self.base_dst = base_dst
        self.verbose = verbose
        self.base_parts = urlparse.urlparse(base_dst)
        self.lock = Lock()

    def write_file(self, rel_path, data):
        "Write file."
        self.lock.acquire()
        try:
            self.write_to_filesystem(rel_path, data)
        finally:
            self.lock.release()

    def write_to_filesystem(self, rel_path, data):
        "Write to file system."
        if self.base_dst == "":
            return
        path = os.path.join(self.base_dst, rel_path)
        print "Writing file %s" % path
        if CREATE_DIRS:
            dir_path, _ = os.path.split(path)
            if dir_path != "" and not os.path.exists(dir_path):
                if self.verbose:
                    print "os.makedirs: %s" % dir_path
                os.makedirs(dir_path)
        with open(path, "wb") as ofh:
            ofh.write(data)

def fetch_file(url):
    "Fetch a specific file via http and return as string."
    try:
        start_time = time.time()
        data = urllib2.urlopen(url).read()
        size = len(data)
        end_time = time.time()
        start_time_tuple = time.gmtime(start_time)
        start_string = time.strftime("%Y-%m-%d-%H:%M:%S", start_time_tuple)
        print "%s  %.3fs for %8dB %s" % (start_string, end_time - start_time, size, url)
    except urllib2.HTTPError, exc:
        print "ERROR %s for %s" % (exc, url)
        data = exc.read()
    # Return a triplet from here
    # data, time duration, size
    return data, end_time - start_time, size


class Fetcher(object):
    "Fetching a complete live DASH session. Must be stopped with interrupt."

    def __init__(self, mpd, base_url=None, file_writer=None, verbose=False):
        self.mpd = mpd
        self.base_url = base_url
        self.file_writer = file_writer
        self.verbose = verbose
        self.fetches = None
        self.threads = []
        self.prepare()
        if mpd.type != "static":
            print "Can only handle static MPDs."
            sys.exit(1)

    def prepare(self):
        "Prepare by gathering info for each representation to download."
        fetches = []
        for adaptation_set in self.mpd.periods[0].adaptation_sets:
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
                            'id' : rep.id}
                fetches.append(rep_data)
        self.fetches = fetches
    
    def start_fetch(self, number_segments=-1):
        "Start a fetch."
        for fetch in self.fetches:
            init_url = os.path.join(fetch['base_url'], fetch['init'])
            # Download the init file first of the lowest bit rate?
            data, _, _ = fetch_file(init_url)
            self.file_writer.write_file(fetch['init'], data)
            thread = FetchThread("SegmentFetcher_%s" % fetch['id'], fetch, self.file_writer, number_segments, self)
            self.threads.append(thread)
            thread.start()

    def getLowestBitRateId(self):
        pass

    def start_fetch_abr(self, number_segments=-1, tp=1):
        # Start initially with the lowest quality
        # 1. Find the lowest bit rate representation id

        # 2. Download the init segment

        # 3. Re-calculate throughput and measure latency.

        # 5. Loop to fetch all the segments utilising Abr(similar to FetchThread) run.
        # Call Abr(throughput). It returns the highest quality id that can be fetched.
        # Now, download the next segment with the given id and re-calculate throughput and latency.
        # Note - we do not need threads until there are multiple adaptation sets i.e. audio and video separate adaptation sets.


class FetchThread(Thread):
    "Thread that fetches media segments."

    def __init__(self, name, fetch, file_writer, nr_segments_to_fetch=-1, fetcher=None):
        self.fetch = fetch
        Thread.__init__(self, name=name)
        self.interrupted = False
        self.file_writer = file_writer
        self.nr_segment_to_fetch = nr_segments_to_fetch
        self.parent = fetcher

    def interrupt(self):
        "Interrupt this thread."
        self.interrupted = True

    def current_number(self, now):
        "Calculate the current segment number."
        return int((now - self.fetch['periodStart']) / self.fetch['dur_s'] + self.fetch['startNr'] - 1)

    def time_for_number(self, number):
        "Calculate the time for a specific segment number."
        return (number - self.fetch['startNr'] - 1) * self.fetch['dur_s'] + self.fetch['periodStart']

    def spec_media(self, number):
        "Return specific media path element."
        return self.fetch['media'].replace("$Number$", str(number))

    def make_media_url(self, number):
        "Make media URL"
        return os.path.join(self.fetch['base_url'], self.spec_media(number))

    def fetch_media_segment(self, number):
        "Fetch a media segment given its number."
        media_url = self.make_media_url(number)
        data, _, _ = fetch_file(media_url)
        return data

    def store_segment(self, data, number):
        "Store the segment to file."
        self.file_writer.write_file(self.spec_media(number), data)

    def run(self):
        "Run this thread."
        cur_seg = 0
        total_segments = self.fetch['periodDuration'] / self.fetch['dur_s']
        while cur_seg < total_segments:
            number = self.fetch['startNr'] + cur_seg
            # Fetch media
            data = self.fetch_media_segment(number)
            self.store_segment(data, number)
            cur_seg += 1


class Abr:
    def __init__(self, config):
        pass
    def get_quality_delay(self, segment_index):
        raise NotImplementedError
    def get_first_quality(self):
        return 0
    def report_delay(self, delay):
        pass
    def report_download(self, metrics, is_replacment):
        pass
    def report_seek(self, where):
        pass
    def check_abandon(self, progress, buffer_level):
        return None

    def quality_from_throughput(self, tput):
        p = manifest.segment_time

        quality = 0
        while (quality + 1 < len(manifest.bitrates) and
               latency + p * manifest.bitrates[quality + 1] / tput <= p):
            quality += 1
        return quality

def download(mpd_url=None, mpd_str=None, base_url=None, base_dst="", number_segments=-1, verbose=False):
    "Download MPD if url specified and then start downloading segments."
    if mpd_url:
        # First download the MPD file
        mpd_str, _, _ = fetch_file(mpd_url)
        base_url, file_name = os.path.split(mpd_url)
        file_writer = FileWriter(base_dst)
        file_writer.write_file(file_name, mpd_str)
    mpd_parser = staticmpdparser.StaticManifestParser(mpd_str)
    fetcher = Fetcher(mpd_parser.mpd, base_url, file_writer, verbose)
    if verbose:
        print str(mpd_parser.mpd)
        print 'fetcher.fetches', fetcher.fetches
    fetcher.start_fetch(number_segments)


def downloadViaAbr(mpd_url=None, mpd_str=None, base_url=None, base_dst="", number_segments=-1, verbose=False):
    "Download MPD first. Then the lowest bitrate init segment. Later depending on throughput and latency, download the highest quality"
    tp = 0
    if mpd_url:
        mpd_str, dur, size = fetch_file(mpd_url)
        # Calculate throughput
        tp = size/dur
        base_url, file_name = os.path.split(mpd_url)
        file_writer = FileWriter(base_dst)
        file_writer.write_file(file_name, mpd_str)
    
    mpd_parser = staticmpdparser.StaticManifestParser(mpd_str)
    fetcher = Fetcher(mpd_parser.mpd, base_url, file_writer, verbose)
    if verbose:
        print str(mpd_parser.mpd)
        print 'fetcher.fetches', fetcher.fetches
    fetcher.start_fetch_abr(number_segments, tp)

def main():
    "Parse command line and start the fetching."
    from optparse import OptionParser
    usage = "usage: %prog [options] mpdURL [dstDir]"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose")
    parser.add_option("-b", "--base_url", dest="baseURLForced")
    parser.add_option("-n", "--number", dest="numberSegments", type="int")
    (options, args) = parser.parse_args()
    number_segments = -1
    if options.numberSegments:
        number_segments = options.numberSegments
    if len(args) < 1:
        parser.error("incorrect number of arguments")
    mpd_url = args[0]
    base_dst = ""
    if len(args) >= 2:
        base_dst = args[1]
    download(mpd_url, base_dst=base_dst, number_segments=number_segments, verbose=options.verbose)
    #downloadViaAbr(mpd_url, base_dst=base_dst, number_segments=number_segments, verbose=options.verbose)


if __name__ == "__main__":
    main()
