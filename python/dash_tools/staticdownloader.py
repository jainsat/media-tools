#!/usr/bin/env python
import os
from common import fetch_file
import staticmpdparser
import client


def download(options, mpd_url=None, mpd_str=None, base_url=None, base_dst=""):
    "Download MPD if url specified and then start downloading segments."
    if mpd_url:
        # First download the MPD file
        mpd_str, _, _ = fetch_file(mpd_url)
        base_url, file_name = os.path.split(mpd_url)
    mpd_parser = staticmpdparser.StaticManifestParser(mpd_str)
    if options.verbose:
        print str(mpd_parser.mpd)

    if options.abr:
        print("Starting ABR client")
        client.AbrClient(mpd_parser.mpd, base_url, base_dst).download()
    elif options.bola:
        print("Starting BOLA client")
        client.BolaClient(mpd_parser.mpd, base_url, base_dst, options).download()
    else:
        print("Starting Simple client")
        client.SimpleClient(mpd_parser.mpd, base_url, base_dst).download()
        


def main():
    "Parse command line and start the fetching."
    from optparse import OptionParser
    usage = "usage: %prog [options] mpdURL [dstDir]"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose")
    parser.add_option("-u", "--base_url", dest="baseURLForced")
    parser.add_option("-a", "--abr", dest="abr", action="store_true")
    parser.add_option("-b", "--bola", dest="bola", action="store_true")
    parser.add_option("-g", "--gp", dest="gp", type="float")
    parser.add_option("-s", "--buffer_size", dest="buffer_size", type="int")
    (options, args) = parser.parse_args()
    if len(args) < 2:
        print(args)
        parser.error("incorrect number of arguments")
    mpd_url = args[0]
    base_dst = ""
    if len(args) >= 2:
        base_dst = args[1]
    
    download(options, mpd_url, base_dst=base_dst)


if __name__ == "__main__":
    main()
