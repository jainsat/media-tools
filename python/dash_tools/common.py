from threading import Thread, Lock
import urllib2
import urlparse
import time
import os
import pdb

CREATE_DIRS = True

def fetch_file(url):
    "Fetch a specific file via http and return as string."
    try:
        start_time = time.time()
        data = urllib2.urlopen(url).read()
        end_time = time.time()
        #size = sys.getsizeof(data)
        size = len(data)
        start_time_tuple = time.gmtime(start_time)
        start_string = time.strftime("%Y-%m-%d-%H:%M:%S", start_time_tuple)
        print "%s  %.3fs for %8dB %s" % (start_string, end_time - start_time, size, url)
    except urllib2.HTTPError, exc:
        print "ERROR %s for %s" % (exc, url)
        data = exc.read()
    # Return a triplet from here
    # data, time duration, size
    return data, end_time - start_time, size

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
        #print "Writing file %s" % path
        if CREATE_DIRS:
            dir_path, _ = os.path.split(path)
            if dir_path != "" and not os.path.exists(dir_path):
                if self.verbose:
                    print "os.makedirs: %s" % dir_path
                os.makedirs(dir_path)
        with open(path, "wb") as ofh:
            ofh.write(data)

class FetchThread(Thread):
    "Thread that fetches media segments."

    def __init__(self, name, rep, file_writer):
        self.file_writer = file_writer
        self.rep = rep
        Thread.__init__(self, name=name)
        #self.parent = fetcher

    def run(self):
        "Run this thread."
        cur_seg = 0
        total_segments = self.rep['periodDuration'] / self.rep['dur_s']
        fetcher = Fetcher(self.file_writer)
        while cur_seg < total_segments:
            number = self.rep['startNr'] + cur_seg
            # Fetch media
            fetcher.fetch(self.rep, number)
            cur_seg += 1


'''
Fetcher class downloads a specific segment of the given 'fetch' type
'''
class Fetcher():
    def __init__(self, file_writer):
        self.file_writer = file_writer

    def spec_media(self, rep, number):
        "Return specific media path element."
        res = rep['media'].replace("$Number$", str(number))
        res = res.replace("$RepresentationID$", rep['id'])
        return res

    def make_media_url(self, rep, number):
        "Make media URL"
        return os.path.join(rep['base_url'], self.spec_media(rep, number))

    def fetch_media_segment(self, rep, number):
        "Fetch a media segment given its number."
        media_url = self.make_media_url(rep, number)
        return fetch_file(media_url)

    def store_segment(self, data, rep, number):
        "Store the segment to file."
        self.file_writer.write_file(self.spec_media(rep, number), data)

    def fetch(self, rep, number):
        # Fetch media
        data, duration, size = self.fetch_media_segment(rep, number)
        self.store_segment(data, rep, number)
        return duration, size
