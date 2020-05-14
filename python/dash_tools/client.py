#!/usr/bin/env python

import staticmpdparser
import common
from threading import Lock
import math
import videoplayer
import os
import pdb
import sys
from collections import OrderedDict


NETFLIX_RESERVOIR = 0.1
NETFLIX_CUSHION = 0.9

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
        self.video_length = mpd.mediaPresentationDuration
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


class Client:

    def download_init_segment(self, config, file_writer):
        # 1. Find the lowest bit rate representation id
        lowQualIndex = config.getLowestBitRateIndex()

        # 2. Download the init segment in lowest quality.
        fetchObj = config.reps[lowQualIndex]
        init_url = os.path.join(fetchObj['base_url'], fetchObj['init'])
        print 'Using bitrate ', config.reps[lowQualIndex]['bandwidth'], ' for initial segment'
        data, duration, size = common.fetch_file(init_url)
        file_writer.write_file(fetchObj['init'], data)
        return duration, size

    def download_video_segment(self, config, fetcher, number):
        # Download in lowest quality.
        lowQualIndex = config.getLowestBitRateIndex()
        return fetcher.fetch(config.reps[lowQualIndex], number)



'''
Download all the representations.
'''
class SimpleClient:
    def __init__(self, mpd, base_url, base_dst):
        # config can be the mpd file
        self.config = Config(mpd, base_url)
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
class AbrClient(Client):
    def __init__(self, mpd, base_url, base_dst, options):
        # config can be the mpd file
        self.config = Config(mpd, base_url)
        self.quality_rep_map = {}
        self.file_writer = common.FileWriter(base_dst)
        for rep in self.config.reps:
            self.quality_rep_map[rep['bandwidth']] = rep
        self.bitrates = self.quality_rep_map.keys()
        self.bitrates.sort()
        utility_offset = -math.log(self.bitrates[0]) # so utilities[0] = 0
        self.utilities = [math.log(b) + utility_offset for b in self.bitrates]
        self.buffer_size = options.buffer_size * 1000
        self.verbose = options.verbose
        # Segment time is in ms
        self.segment_time = self.config.reps[0]['dur_s']*1000
        self.player = videoplayer.VideoPlayer(self.segment_time, self.config.video_length, self.utilities, self.bitrates)

    def quality_from_throughput(self, tput):
        # in seconds
        segment_time = self.config.reps[0]['dur_s']
        quality = 0
        bitrates = self.quality_rep_map.keys() 
        bitrates.sort()
        while (quality + 1 < len(bitrates) and ((segment_time * bitrates[quality + 1])/tput) <= segment_time):
            quality += 1
        return bitrates[quality], quality

    def download(self):
        throughput = 0
        # download init segment
        duration, size = self.download_init_segment(self.config, self.file_writer)
        fetcher = common.Fetcher(self.file_writer)
        startNumber = self.config.reps[0]['startNr'] 
        # Download the first segment with lowest quality
        duration, size = self.download_video_segment(self.config, fetcher, startNumber)

        # Re-calculate throughput and measure latency.
        throughput = size/duration
        # Add the lowest quality to the buffer for first segment
        self.player.buffer_contents += [0]
        self.player.total_play_time += duration * 1000
        if self.verbose:
           print "Downloaded first segment"
      
        total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
        cur_seg = 1
        # Using index 0 - ASSUMPTION - all representation set have same duration and same start number
        # Note - we do not need threads until there are multiple adaptation sets i.e. audio and video separate adaptation sets.
        while cur_seg < total_segments:
            number = startNumber + cur_seg
            #if buffer is full
            bufferOverflow = self.player.get_buffer_level() + self.segment_time - self.buffer_size
            if bufferOverflow > 0:
               print "Buffer full"
               self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)

            # Call Abr(throughput). It returns the highest quality id that can be fetched.
            bitrateQuality, quality = self.quality_from_throughput(throughput)
            print 'Using quality', quality, 'for segment', cur_seg, 'based on throughput ', throughput

            # Use the quality as index to fetch the media
            # quality directly corresponds to the index in self.fetches
            duration, size = fetcher.fetch(self.quality_rep_map[bitrateQuality], number)

            self.player.deplete_buffer(int(duration * 1000))
            self.player.buffer_contents += [quality]
            # Recalculate throughput
            throughput = size/duration
            cur_seg += 1

        self.player.deplete_buffer(self.player.get_buffer_level())
        print("Total play time = %d sec" % (self.player.total_play_time/1000))
        print('Total played utility: %f' % self.player.played_utility)
        print('Avg played bitrate: %f' % (self.player.played_bitrate / total_segments))
        print('Rebuffer time = %f sec' % (self.player.rebuffer_time / 1000))        
        print('Rebuffer count = %d' % self.player.rebuffer_event_count)

class BolaClient(Client):

    def __init__(self, mpd, base_url, base_dst, options):
        self.config = Config(mpd, base_url)
        self.quality_rep_map = {}
        self.file_writer = common.FileWriter(base_dst)
        for rep in self.config.reps:
            self.quality_rep_map[rep['bandwidth']] = rep
        self.bitrates = self.quality_rep_map.keys()
        self.bitrates.sort()
        utility_offset = -math.log(self.bitrates[0]) # so utilities[0] = 0
        self.utilities = [math.log(b) + utility_offset for b in self.bitrates]
        self.verbose = options.verbose
        self.gp = options.gp
        # buffer_size is in ms
        self.buffer_size = options.buffer_size * 1000
        print "buffer = ", self.buffer_size, "gp = ", self.gp
        #self.abr_osc = config['abr_osc']
        #self.abr_basic = config['abr_basic']

        # Segment time is in ms
        self.segment_time = self.config.reps[0]['dur_s']*1000
        self.Vp = (self.buffer_size - self.segment_time) / (self.utilities[-1] + self.gp)
        self.player = videoplayer.VideoPlayer(self.segment_time, self.config.video_length, self.utilities, self.bitrates)
        #self.last_seek_index = 0 # TODO
        #self.last_quality = 0
        if options.verbose:
            for q in range(len(self.bitrates)):
                b = self.bitrates[q]
                u = self.utilities[q]
                l = self.Vp * (self.gp + u)
                if q == 0:
                    print('%d %d' % (q, l))
                else:
                    qq = q - 1
                    bb = self.bitrates[qq]
                    uu = self.utilities[qq]
                    ll = self.Vp * (self.gp + (b * uu - bb * u) / (b - bb))
                    print('%d %d    <- %d %d' % (q, l, qq, ll))

    def quality_from_buffer(self):
        level = self.player.get_buffer_level()
        quality = 0
        score = None
        for q in range(len(self.bitrates)):
            s = ((self.Vp * (self.utilities[q] + self.gp) - level) / self.bitrates[q])
            if score == None or s > score:
                quality = q
                score = s
        return quality

    def download(self):
        # download init segment
       self.download_init_segment(self.config, self.file_writer)
       fetcher = common.Fetcher(self.file_writer)

       # Download the first segment
       duration, size = self.download_video_segment(self.config, fetcher, 1)
       # Add the lowest quality to the buffer for first segment
       self.player.buffer_contents += [0]
       self.player.total_play_time += duration * 1000
       if self.verbose:
           print "Downloaded first segment\n"
       total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
       next_seg = 2
       while next_seg <= total_segments:
           #if buffer is full
           bufferOverflow = self.player.get_buffer_level() + self.segment_time - self.buffer_size
           if bufferOverflow > 0:
               self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)

           quality = self.quality_from_buffer()
           print 'Using quality', quality, 'for segment', next_seg, 'based on quality', quality

           duration, size = fetcher.fetch(self.quality_rep_map[self.bitrates[quality]], next_seg)
           self.player.deplete_buffer(int(duration * 1000))
           self.player.buffer_contents += [quality]
           next_seg += 1

       self.player.deplete_buffer(self.player.get_buffer_level())
       print("Total play time = %d sec" % (self.player.total_play_time/1000))
       print('total played utility: %f' % self.player.played_utility)
       print('Avg played bitrate: %f' % (self.player.played_bitrate / total_segments))
       print('Rebuffer time = %f sec' % (self.player.rebuffer_time / 1000))        
       print('Rebuffer count = %d' % self.player.rebuffer_event_count)



class BBAClient(Client):

    def __init__(self, mpd, base_url, base_dst, options):
        self.config = Config(mpd, base_url)
        self.quality_rep_map = {}
        self.file_writer = common.FileWriter(base_dst)
        for rep in self.config.reps:
            self.quality_rep_map[rep['bandwidth']] = rep
        self.bitrates = self.quality_rep_map.keys()
        self.bitrates.sort()
        utility_offset = -math.log(self.bitrates[0]) # so utilities[0] = 0
        self.utilities = [math.log(b) + utility_offset for b in self.bitrates]
        self.verbose = options.verbose
        self.gp = options.gp
        self.rate_map = self.get_rate_map()
        # buffer_size is in ms
        self.buffer_size = options.buffer_size * 1000

        # Segment time is in ms
        self.segment_time = self.config.reps[0]['dur_s']*1000
        self.player = videoplayer.VideoPlayer(self.segment_time, self.config.video_length, self.utilities, self.bitrates)

    def get_rate_map(self):
        """
        Module to generate the rate map for the bitrates, reservoir, and cushion
        """
        rate_map = OrderedDict()
        rate_map[NETFLIX_RESERVOIR] = 0
        #intermediate_levels = self.bitrates[1:-1]
        blen = len(self.bitrates)
        marker_length = (NETFLIX_CUSHION - NETFLIX_RESERVOIR)/(blen - 1)
        current_marker = NETFLIX_RESERVOIR + marker_length
        for quality in range(1, blen-1):
            rate_map[current_marker] = quality
            current_marker += marker_length
        rate_map[NETFLIX_CUSHION] = blen - 1
        return rate_map

    def get_quality_netflix(self, rate_map=None):
        """
        Module that estimates the next bitrate basedon the rate map.
        Rate Map: Buffer Occupancy vs. Bitrates:
            If Buffer Occupancy < RESERVOIR (10%) :
                select the minimum bitrate
            if RESERVOIR < Buffer Occupancy < Cushion(90%) :
                Linear function based on the rate map
            if Buffer Occupancy > Cushion :
                Maximum Bitrate
        Ref. Fig. 6 from [1]
        :param current_buffer_occupancy: Current buffer occupancy in number of segments
        :param bitrates: List of available bitrates [r_min, .... r_max]
        :return:the bitrate for the next segment
        """
        next_bitrate = None
        # Calculate the current buffer occupancy percentage
        try:
            buffer_percentage = self.player.get_buffer_level()/self.buffer_size
            print buffer_percentage
        except ZeroDivisionError:
            print "Buffer Size was found to be Zero"
            return None
        # Selecting the next bitrate based on the rate map
        print "buffer percentage = ", buffer_percentage        
        if buffer_percentage <= NETFLIX_RESERVOIR:
            next_bitrate = 0
        elif buffer_percentage >= NETFLIX_CUSHION:
            next_bitrate = len(self.bitrates) - 1
        else:
            if self.verbose:
                print "Rate Map: {}".format(self.rate_map)
            for marker in reversed(self.rate_map.keys()):
                #print "comparing marker ", marker, " and ", buffer_percentage
                if marker < buffer_percentage:
                    break
                next_bitrate = self.rate_map[marker]
        return next_bitrate


    def download(self):
        # download init segment
       self.download_init_segment(self.config, self.file_writer)
       fetcher = common.Fetcher(self.file_writer)

       # Download the first segment
       duration, size = self.download_video_segment(self.config, fetcher, 1)
       # Add the lowest quality to the buffer for first segment
       self.player.buffer_contents += [0]
       self.player.total_play_time += duration * 1000
       if self.verbose:
           print "Downloaded first segment\n"
       total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
       next_seg = 2
       while next_seg <= total_segments:
           #if buffer is full
           bufferOverflow = self.player.get_buffer_level() + self.segment_time - self.buffer_size
           if bufferOverflow > 0:
               self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)

           quality = self.get_quality_netflix()
           print 'Using quality ', quality, 'for segment ', next_seg, 'based on quality ', quality

           duration, size = fetcher.fetch(self.quality_rep_map[self.bitrates[quality]], next_seg)
           self.player.deplete_buffer(int(duration * 1000))
           self.player.buffer_contents += [quality]
           next_seg += 1

       self.player.deplete_buffer(self.player.get_buffer_level())
       print("Total play time = %d sec" % (self.player.total_play_time/1000))
       print('total played utility: %f' % self.player.played_utility)
       print('Avg played bitrate: %f' % (self.player.played_bitrate / total_segments))
       print('Rebuffer time = %f sec' % (self.player.rebuffer_time / 1000))
       print('Rebuffer count = %d' % self.player.rebuffer_event_count)
