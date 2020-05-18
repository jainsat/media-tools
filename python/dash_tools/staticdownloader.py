#!/usr/bin/env python
import os
from common import fetch_file
import staticmpdparser
import client
import json
import pdb

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
        client.AbrClient(mpd_parser.mpd, base_url, base_dst, options).download()
    elif options.bola:
        print("Starting BOLA client")
        client.BolaClient(mpd_parser.mpd, base_url, base_dst, options).download()
    elif options.bba0:
        print("Starting BBA0 client")
        client.BBAClient(mpd_parser.mpd, base_url, base_dst, options).download_bba0()
    elif options.bba2:
        print("Starting BBA2 client")
        client.BBAClient(mpd_parser.mpd, base_url, base_dst, options).download_bba2()
    elif options.pensieve:
        print("Starting Pensieve client")
        client.PensieveClient(mpd_parser.mpd, base_url, base_dst, options).download_pensieve()
    else:
        print("Starting Simple client")
        client.SimpleClient(mpd_parser.mpd, base_url, base_dst).download()

def main():
    "Parse command line and start the fetching."
    from optparse import OptionParser
    usage = "usage: %prog [options] mpdURL [dstDir]"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose")
    parser.add_option("-a", "--abr", dest="abr", action="store_true")
    parser.add_option("-b", "--bola", dest="bola", action="store_true")
    parser.add_option("-B", "--bba0", dest="bba0", action="store_true")
    parser.add_option("-X", "--bba2", dest="bba2", action="store_true")
    parser.add_option("-p", "--pensieve", dest="pensieve", action="store_true")
    parser.add_option("-g", "--gp", dest="gp", type="float", default=5,
                      help = 'Specify the (gamma p) product in seconds.')
    parser.add_option("-s", "--buffer_size", dest="buffer_size", type="int", default=20,
                      help='Specify the buffer size in seconds')
    parser.add_option("-C", "--bandwidthchangerscript", dest="bandwidth_changerscript_path", type="str",
                      default="./trigger_bandwidth_changer.sh", help='Specify the bandwidth changer script to trigger the remote program on server that runs tc on a network trace')
    (options, args) = parser.parse_args()
    if len(args) < 1:
        parser.error("incorrect number of arguments")
        print(usage)

    # MPD url can be of the form http://10.128.0.33:5000/manifest.mpd
    mpd_url = args[0]
    base_dst = "download"
    if len(args) >= 2:
        base_dst = args[1]
    download(options, mpd_url, base_dst=base_dst)

if __name__ == "__main__":
    main()
