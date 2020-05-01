#!/usr/bin/env python

import staticmpdparser
import common
from threading import Lock
import math
import videoplayer
import os


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
class AbrClient(Client):
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
        while (quality + 1 < len(bitrates) and \
            ((segment_time * bitrates[quality + 1])/tput) <= segment_time):
            quality += 1
        return bitrates[quality]

    def download(self):
        throughput = 0

        duration, size = self.download_init_segment(self.config, self.file_writer)

        # Re-calculate throughput and measure latency.
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


class BolaClient(Client):

    def __init__(self, mpd, base_url, base_dst, options):
        self.config = Config(mpd, base_url);
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
        self.buffer_size = options.buffer_size
        #self.abr_osc = config['abr_osc']
        #self.abr_basic = config['abr_basic']
        segment_time = self.config.reps[0]['dur_s']
        self.Vp = (self.buffer_size - segment_time) / (self.utilities[-1] + self.gp)
        self.player = videoplayer.VideoPlayer(segment_time*1000, self.utilities, self.bitrates)
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
        # downlod init segment
       self.download_init_segment(self.config, self.file_writer)
       fetcher = common.Fetcher(self.file_writer)
       duration, size = self.download_video_segment(self.config, fetcher, 1)
       self.player.total_play_time += duration * 1000
       if self.verbose:
           print "Downloaded first segment\n"
       total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
       next_seg = 2
       while next_seg <= total_segments:
           #if buffer is full
           if self.player.get_buffer_level() == self.buffer_size:
               self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)

           quality = self.quality_from_buffer()
           print 'Using bitrate ', quality, 'for segment', next_seg, 'based on throughput ', quality

           duration, size = fetcher.fetch(self.quality_rep_map[self.bitrates[quality]], next_seg)
           self.player.deplete_buffer(int(duration * 1000))
           self.player.buffer_contents += [quality]
           next_seg += 1

       self.player.deplete_buffer(self.player.get_buffer_level())
       print("Total play time = %d sec" % (self.player.total_play_time/1000))
       print('total played utility: %f' % self.player.played_utility)
       print('Avg played bitrate: %f' % (self.player.played_bitrate / total_segments))
       print('Rebuffer time = %f sec' % (self.player.rebuffer_time / 1000))        
       print('Rebuffer time = %d' % self.player.rebuffer_event_count)        

    

       



