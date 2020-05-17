import math

class VideoPlayer:
    def __init__(self, segment_time, utilities, bitrates):
        self.segment_time = segment_time
        self.utilities = utilities
        self.bitrates = bitrates
        self.buffer_contents = []
        self.buffer_fcc = 0
        self.rebuffer_time = 0
        self.total_play_time = 0
        self.played_utility = 0
        self.played_bitrate = 0
        self.last_played = None
        self.total_bitrate_change = 0
        self.total_log_bitrate_change = 0
        self.rebuffer_event_count = 0
    
    def get_buffer_level(self):
        return self.segment_time * len(self.buffer_contents) - self.buffer_fcc

    def deplete_buffer(self, time):
        #print("len = %d " % len(self.buffer_contents))
        #print("segment time = %d" % self.segment_time)
        if len(self.buffer_contents) == 0:
            self.rebuffer_time += time
            self.total_play_time += time
            return

        if self.buffer_fcc > 0:
            # first play any partial chunk left

            if time + self.buffer_fcc < self.segment_time:
                self.buffer_fcc += time
                self.total_play_time += time
                return

            time -= self.segment_time - self.buffer_fcc
            self.total_play_time += self.segment_time - self.buffer_fcc
            self.buffer_contents.pop(0)
            self.buffer_fcc = 0

        # buffer_fcc == 0 if we're here

        while time > 0 and len(self.buffer_contents) > 0:
            quality = self.buffer_contents[0]
            self.played_utility += self.utilities[quality]
            self.played_bitrate += self.bitrates[quality]
            if quality != self.last_played and self.last_played != None:
                self.total_bitrate_change += abs(self.bitrates[quality] -
                                              self.bitrates[self.last_played])
                #self.total_log_bitrate_change += abs(math.log(self.bitrates[quality] /
                #                                                     self.bitrates[self.last_played]))
            self.last_played = quality

            if time >= self.segment_time:
                self.buffer_contents.pop(0)
                self.total_play_time += self.segment_time
                time -= self.segment_time
            else:
                # Play only when we have a complete segment in our buffer
                self.buffer_fcc = time
                self.total_play_time += time
                time = 0

        if time > 0.000001:
            print("Increasing rebuffer", time)
            self.rebuffer_time += time
            self.total_play_time += time
            self.rebuffer_event_count += 1

