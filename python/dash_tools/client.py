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

import os
os.environ['CUDA_VISIBLE_DEVICES']=''

import numpy as np
import tensorflow as tf
import a3c

## The following parameters are specific to Pensieve ABR
S_INFO = 6  # bit_rate, buffer_size, rebuffering_time, bandwidth_measurement, chunk_til_video_end
S_LEN = 8  # take how many frames in the past
A_DIM = 6
ACTOR_LR_RATE = 0.0001
CRITIC_LR_RATE = 0.001

NN_MODEL = './pensieve_pretrained_models/pretrain_linear_reward.ckpt'
DEFAULT_QUALITY = 0  # default video quality without agent
M_IN_K = 1000.0
REBUF_PENALTY = 4.3  # 1 sec rebuffering -> this number of Mbps
SMOOTH_PENALTY = 1
RAND_RANGE = 1000
## TODO - change this
#VIDEO_BIT_RATE = [300,750,1200,1850,2850,4300]
BUFFER_NORM_FACTOR = 10.0
## End of Pensieve parameters

NETFLIX_INITIAL_BUFFER = 2
NETFLIX_RESERVOIR = 0.1
NETFLIX_CUSHION = 0.9
NETFLIX_INITIAL_FACTOR = 0.875

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
            # Check if the given rep has segment_template or else use parent
            segment_template = adaptation_set.segment_template
            if hasattr(rep, 'segment_template'):
                media = rep.segment_template.media
                segment_template = rep.segment_template
            else:
                media = adaptation_set.segment_template.media

            rep_data = {'init' : init, 'media' : media,
                        'duration' : segment_template.duration,
                        'timescale' : segment_template.timescale,
                        'dur_s' : (segment_template.duration * 1.0 /
                                   segment_template.timescale),
                        'startNr' : segment_template.startNumber,
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
        # If there is a representationID, then replace it with least rep id
        initName = fetchObj['init'].replace("$RepresentationID$", "video6")
        init_url = os.path.join(fetchObj['base_url'], initName)
        print 'Using bitrate ', config.reps[lowQualIndex]['bandwidth'], ' for initial segment'
        print 'init url', init_url
        data, duration, size = common.fetch_file(init_url)
        file_writer.write_file(initName, data)
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
        self.player = videoplayer.VideoPlayer(self.segment_time, self.utilities, self.bitrates)

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
        self.player = videoplayer.VideoPlayer(self.segment_time, self.utilities, self.bitrates)
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

    def __init__(self, mpd, base_url, base_dst, options, segment_sizes=None):
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
        self.segment_sizes = segment_sizes
        self.rate_map = self.get_rate_map()
        # buffer_size is in ms
        self.buffer_size = options.buffer_size * 1000

        # Segment time is in ms
        self.segment_time = self.config.reps[0]['dur_s']*1000
        self.player = videoplayer.VideoPlayer(self.segment_time, self.utilities, self.bitrates)

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

    def get_quality_bba2(self, average_segment_sizes, segment_download_rate, curr_bitrate, state):
        available_video_segments = self.player.get_buffer_level()
        if state == "INITIAL":
            # if the B increases by more than 0.875V s. Since B = V - ChunkSize/c[k],
            # B > 0:875V also means that the chunk is downloaded eight times faster than it is played
            next_bitrate = curr_bitrate
            # delta-B = V - ChunkSize/c[k]
            print "curr bit rate = ", curr_bitrate, " download rate = ", segment_download_rate
            delta_B = (self.segment_time/1000) - average_segment_sizes[curr_bitrate]/segment_download_rate
            # Select the higher bitrate as long as delta B > 0.875 * V
            if delta_B > NETFLIX_INITIAL_FACTOR * self.segment_time:
                next_bitrate = self.bitrates.index(curr_bitrate)+1
            # if the current buffer occupancy is less that NETFLIX_INITIAL_BUFFER, then do NOY use rate map
            if not available_video_segments < NETFLIX_INITIAL_BUFFER:

                # get the next bitrate based on the ratemap
                rate_map_next_bitrate = self.get_quality_netflix()
                # Consider the rate map only if the rate map gives a higher value.
                # Once the rate mao returns a higher value exit the 'INITIAL' stage
                if rate_map_next_bitrate > next_bitrate:
                    next_bitrate = rate_map_next_bitrate
                    state = "RUNNING"
        else:
            next_bitrate = self.get_quality_netflix()
        return next_bitrate, state



    def download_bba0(self):
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

    def get_average_segment_sizes(self):
        """
        Module to get the avearge segment sizes for each bitrate
        :param dp_object:
        :return: A dictionary of aveage segment sizes for each bitrate
        """
        average_segment_sizes = dict()
        for quality in range(len(self.bitrates)):
            segment_sizes = [ sizes[quality] for sizes in self.segment_sizes]
            segment_sizes = [float(i) for i in segment_sizes]
            try:
                average_segment_sizes[quality] = sum(segment_sizes)/len(segment_sizes)
            except ZeroDivisionError:
                average_segment_sizes[quality] = 0
        print "The avearge segment size for is {}".format(average_segment_sizes.items())
        return average_segment_sizes


    def download_bba2(self):
       # download init segment
       self.download_init_segment(self.config, self.file_writer)
       fetcher = common.Fetcher(self.file_writer)

       # get average segment sizes.
       average_segment_sizes = self.get_average_segment_sizes()
      
      
       # Download the first segment
       duration, size = self.download_video_segment(self.config, fetcher, 1)
       # Add the lowest quality to the buffer for first segment
       self.player.buffer_contents += [0]
       self.player.total_play_time += duration * 1000
       
       segment_size = segment_download_time  = None
       state = "INITIAL"
       total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']
       next_seg = 2
       curr_bitrate = 0
       segment_download_rate = size / duration
       while next_seg <= total_segments:
           #if buffer is full
           bufferOverflow = self.player.get_buffer_level() + self.segment_time - self.buffer_size
           if bufferOverflow > 0:
               print "overflow"
               self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)

           if segment_size and segment_download_time:
               segment_download_rate = segment_size / segment_download_time
           
           curr_bitrate, state = self.get_quality_bba2(average_segment_sizes, segment_download_rate, curr_bitrate, state)
           quality = curr_bitrate
           print 'Using quality ', quality, 'for segment ', next_seg, 'based on quality ', quality

           segment_download_time, segment_size = fetcher.fetch(self.quality_rep_map[self.bitrates[quality]], next_seg)
           self.player.deplete_buffer(int(segment_download_time * 1000))
           self.player.buffer_contents += [quality]
           next_seg += 1

       self.player.deplete_buffer(self.player.get_buffer_level())
       print("Total play time = %d sec" % (self.player.total_play_time/1000))
       print('total played utility: %f' % self.player.played_utility)
       print('Avg played bitrate: %f' % (self.player.played_bitrate / total_segments))
       print('Rebuffer time = %f sec' % (self.player.rebuffer_time / 1000))
       print('Rebuffer count = %d' % self.player.rebuffer_event_count)

class PensieveClient(Client):
    #def __init__(self, config):
    def __init__(self, mpd, base_url, base_dst, options, segment_sizes):
        self.config = Config(mpd, base_url)
        self.quality_rep_map = {}
        self.file_writer = common.FileWriter(base_dst)

        for rep in self.config.reps:
            self.quality_rep_map[rep['bandwidth']] = rep

        self.bitrates = self.quality_rep_map.keys()
        self.bitrates.sort()
        print "ritz", self.bitrates, self.quality_rep_map
        VIDEO_BIT_RATE = self.bitrates
        utility_offset = -math.log(self.bitrates[0])
        self.utilities = [math.log(b) + utility_offset for b in self.bitrates]
        self.buffer_size = options.buffer_size * 1000
        self.verbose = options.verbose
        self.segments = segment_sizes
        self.segment_time = self.config.reps[0]['dur_s']*1000
        self.player = videoplayer.VideoPlayer(self.segment_time,
                self.utilities, self.bitrates)

        self.sess = tf.Session()

        self.actor = a3c.ActorNetwork(self.sess, state_dim=[S_INFO, S_LEN], action_dim=A_DIM, learning_rate=ACTOR_LR_RATE)
        self.critic = a3c.CriticNetwork(self.sess, state_dim=[S_INFO, S_LEN], learning_rate=CRITIC_LR_RATE)

        self.sess.run(tf.initialize_all_variables())
        self.saver = tf.train.Saver()

        # restore neural net parameters
        self.nn_model = NN_MODEL
        if self.nn_model is not None:  # nn_model is the path to file
            self.saver.restore(self.sess, self.nn_model)
            print("Model restored.")

        self.init_action = np.zeros(A_DIM)
        self.init_action[DEFAULT_QUALITY] = 1

        self.s_batch = [np.zeros((S_INFO, S_LEN))]
        self.a_batch = [self.init_action]
        self.r_batch = []

        self.train_counter = 0

        self.last_quality = DEFAULT_QUALITY
        self.last_bit_rate = DEFAULT_QUALITY
        self.last_total_rebuf = 0
        # need this storage, because observation only contains total rebuffering time
        # we compute the difference to get

        self.video_chunk_count = 0
        self.chunk_fetch_time = 0
        self.chunk_size = 0
        self.rebuffer_time = 0

    def get_chunk_size(self, quality, segment_index):
        #pdb.set_trace()
        if segment_index+A_DIM <= len(self.segments):
            print "segment index getting fetched:", segment_index, quality
            return self.segments[segment_index][quality]
        else:
            return 0

    def get_quality_delay(self, segment_index):
        self.rebuffer_time = float(self.rebuffer_time - self.last_total_rebuf)
        reward = self.bitrates[self.last_quality] / M_IN_K - REBUF_PENALTY * self.rebuffer_time / M_IN_K - SMOOTH_PENALTY * np.abs(self.bitrates[self.last_quality] - self.last_bit_rate) / M_IN_K

        self.last_bit_rate = self.bitrates[self.last_quality]
        self.last_total_rebuf = self.rebuffer_time

        # retrieve previous state
        if len(self.s_batch) == 0:
            state = [np.zeros((S_INFO, S_LEN))]
        else:
            state = np.array(self.s_batch[-1], copy=True)

        # compute bandwidth measurement
        video_chunk_fetch_time = self.chunk_fetch_time
        video_chunk_size = self.chunk_size

        total_segments = self.config.reps[0]['periodDuration'] / self.config.reps[0]['dur_s']

        # compute number of video chunks left
        video_chunk_remain = len(self.segments) - self.video_chunk_count
        self.video_chunk_count += 1

        # dequeue history record
        state = np.roll(state, -1, axis=1)

        next_video_chunk_sizes = []
        for i in range(A_DIM):
            next_video_chunk_sizes.append(self.get_chunk_size(i, self.video_chunk_count))

        # this should be S_INFO number of terms
        try:
            state[0, -1] = self.bitrates[self.last_quality] / float(np.max(self.bitrates))
            state[1, -1] = get_buffer_level() / BUFFER_NORM_FACTOR
            state[2, -1] = float(video_chunk_size) / float(video_chunk_fetch_time) / M_IN_K  # kilo byte / ms
            state[3, -1] = float(video_chunk_fetch_time) / M_IN_K / BUFFER_NORM_FACTOR  # 10 sec
            state[4, :A_DIM] = np.array(next_video_chunk_sizes) / M_IN_K / M_IN_K  # mega byte
            state[5, -1] = np.minimum(video_chunk_remain, len(self.segments)) / float(len(self.segments))
        except ZeroDivisionError:
            # this should occur VERY rarely (1 out of 3000), should be a dash issue
            # in this case we ignore the observation and roll back to an eariler one
            if len(self.s_batch) == 0:
                state = [np.zeros((S_INFO, S_LEN))]
            else:
                state = np.array(self.s_batch[-1], copy=True)

        action_prob = self.actor.predict(np.reshape(state, (1, S_INFO, S_LEN)))
        action_cumsum = np.cumsum(action_prob)
        bit_rate = (action_cumsum > np.random.randint(1, RAND_RANGE) / float(RAND_RANGE)).argmax()
        # Note: we need to discretize the probability into 1/RAND_RANGE steps,
        # because there is an intrinsic discrepancy in passing single state and batch states

        print("Pensieve", bit_rate, self.video_chunk_count)
        #quality = np.random.randint(2)#get_quality(str(bit_rate))
        quality = bit_rate

        # record [state, action, reward]
        # put it here after training, notice there is a shift in reward storage
        if self.video_chunk_count >= len(self.segments):
            self.s_batch = [np.zeros((S_INFO, S_LEN))]
        else:
            self.s_batch.append(state)

        self.last_quality = quality

        return quality

    def download_pensieve(self):
        # Download init segment
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
            bufferOverflow = self.player.get_buffer_level() + self.segment_time  - self.buffer_size
            if bufferOverflow > 0:
                self.player.deplete_buffer(self.config.reps[0]['dur_s'] * 1000)
            # Change here
            quality = self.get_quality_delay(next_seg)
            print 'Using quality ', quality, 'for segment ', next_seg

            #pdb.set_trace()
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

