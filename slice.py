#!/usr/bin/env python3
import subprocess
import csv
import datetime
import argparse
import os
from unidecode import unidecode


def configure():
    parser = argparse.ArgumentParser(description='Cut up audio/video clips using timestamps from a .csv file')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--audio', metavar='\b', type=str, help='audio file to cut')
    group.add_argument('-v', '--video', metavar='\b', type=str, help='video file to cut')
    parser.add_argument('-k', '--key', metavar='\b', type=str, help='csv file with timestamps')
    parser.add_argument('-f', '--fuzz', metavar='\b', type=float, default=0, help='add seconds to either end of each clip')
    args = parser.parse_args()
    return(args)


def import_data(path):
    with open(path, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        fn = csv_reader.fieldnames
        tsdata = [(x[fn[0]], x[fn[1]], x[fn[2]]) for i, x in enumerate(csv_reader)]
    return(tsdata)


def parse_data_ffmpeg(tsdata, fuzz):
    """gets timestamps ready for use in the arguments passed to ffmpeg"""
    tsconv = [(fz(parse_secs(x), fuzz, '-'), fz(parse_secs(y), fuzz)) for x, y, z in tsdata]
    return(tsconv)


def parse_data_key(tsdata, fuzz):
    tsconv_keys = [(fz(parse_secs(x), fuzz, '-'), fz(parse_secs(y), fuzz), lab) for x, y, lab in tsdata]
    # timeshifting the output to csv
    tsmin = min(tsconv_keys, key=lambda x: x[0])[0]
    # shifts so it starts at zero
    tsshift = [(x - tsmin, y - tsmin, y - x, lab) for x, y, lab in tsconv_keys]
    # sorting it so it matches the ffmpeg output
    tsshift = sorted(tsshift, key=lambda x: x[0])
    # shift to remove the gaps bewtween the clips
    ts_keys = []
    for i, (ts1, ts2, dur, lab) in enumerate(tsshift):
        if i == 0:
            prev_ts2 = 0
        else:
            prev_ts2 = ts_keys[i - 1][1]
        ts1_shift = prev_ts2
        ts2_shift = prev_ts2 + dur
        ts_keys.append((ts1_shift, ts2_shift, lab))
    tsshift_key = [(conv_time(x), conv_time(y), unidecode(lab)) for x, y, lab in ts_keys]
    return(tsshift_key)


def conv_time(input):
    """method for converting .srt time strings to number of seconds"""
    if isinstance(input, float) or isinstance(input, int):
        if input == 0:
            return('00:00:00,000')
        else:
            time = str(datetime.timedelta(seconds=input))
            time = time.replace(".", ",")  # second to milisecond separator is a comma in .srt
            if len(time) in (6, 7):
                time = time + ',000000'  # sometimes the microseconds are not added
            time = time[:-3]  # converts from microseconds to miliseconds
            time = time.rjust(12, '0')  # will add extra zero if hours are missing them
            return(time)
    elif isinstance(input, str):
        time = input
        if time == '00:00:00,000':
            return(float(0))
        else:
            time_struct = datetime.datetime.strptime(input, "%H:%M:%S,%f")
            td = time_struct - datetime.datetime(1900, 1, 1)
            time_float = float(td.total_seconds())
            return(time_float)


def write_key(key, filein):
    fileout = output_filename(filein)
    with open(fileout, mode='w') as key_file:
        key_writer = csv.writer(key_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        key_writer.writerow(['ts1', 'ts2', 'clip_description'])
        for row in key:
            key_writer.writerow(row)


def ts_to_cmd(ts, filein, av):
    fileout = output_filename(filein)
    cmd = [f'between(t,{x},{y})' for x, y in ts]
    cmd = '+'.join(cmd)
    vcmd = f"select='{cmd}',setpts=N/FRAME_RATE/TB"
    acmd = f"aselect='{cmd}',asetpts=N/SR/TB"
    if av == 'video':
        cmd_tup = (
            'ffmpeg',
            '-y',  # overwrites files by default
            '-i', filein,
            '-vf', vcmd,
            '-af', acmd,
            fileout
        )
    elif av == 'audio':
        cmd_tup = (
            'ffmpeg',
            '-y',  # overwrites files by default
            '-i', filein,
            '-af', acmd,
            fileout
        )
    return(cmd_tup)

# utilities used by other functions


def output_filename(filein):
    basename, ext = os.path.splitext(filein)
    fileout = basename + '_out' + ext
    return(fileout)


def parse_secs(ts):
    time_formats = {
        4: '%M:%S',
        5: '%M:%S',
        8: '%H:%M:%S',
        9: '%M:%S.%f',
        12: '%H:%M:%S.%f'
    }
    time_struct = datetime.datetime.strptime(ts, time_formats.get(len(ts)))
    td = time_struct - datetime.datetime(1900, 1, 1)
    tf = float(td.total_seconds())
    return(tf)


def fz(ts, fuzz, func='+'):
    if func == '+':
        ts += fuzz
    elif func == '-':
        ts -= fuzz
    if ts <= 0:
        return(0)
    else:
        return(ts)


def main():
    args = configure()
    if args.audio:
        type = 'audio'
    elif args.video:
        type = 'video'
    input = args.__getattribute__(type)
    ts_raw = import_data(args.key)
    ts_ffmpeg = parse_data_ffmpeg(ts_raw, args.fuzz)
    ts_key = parse_data_key(ts_raw, args.fuzz)
    cmd = ts_to_cmd(ts_ffmpeg, input, type)
    write_key(ts_key, args.key)
    subprocess.Popen(cmd, shell=False, close_fds=True)


if __name__ == "__main__":
    main()
