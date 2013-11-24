#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import uuid
import logging
from glob import glob

import pld_nr_buildconf

logger = logging.getLogger("make_module")

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Make PLD NR module",
                                     parents=[log_parser])
    parser.add_argument("module", action="store",
                        help="Module name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    lst_fn = "{0}.lst".format(args.module)
    exclude_fn = "{0}.exclude".format(args.module)
    squashfs_fn = "{0}.sqf".format(args.module)

    if os.path.exists(squashfs_fn):
        os.unlink(squashfs_fn)

    logger.debug("Getting list of all files in 'root'")
    find_p = subprocess.Popen(config.c_sudo + ["find", "root"],
                                stdout=subprocess.PIPE)
    all_files = [l.strip(b"root/").decode("utf-8").rstrip()
                                        for l in find_p.stdout.readlines()]
    find_p.stdout.close()
    rc = find_p.wait()
    if rc:
        raise CalledProcessError(rc, ["find", "root"])

    all_files = set(f for f in all_files if f)

    module_files = set(l.rstrip() for l in open(lst_fn, "rt").readlines())
    module_dirs = set()
    for path in module_files:
        while "/" in path:
            path = path.rsplit("/", 1)[0]
            module_dirs.add(path)
    
    logger.debug("Building the exclude file")
    excludes = all_files - module_files - module_dirs
    excludes = sorted(excludes)
    while excludes and not excludes[0]:
        # squashfs hates empty paths
        excludes = excludes[1:]
    with open(exclude_fn, "wt") as exclude_f:
        exclude_f.writelines(e + "\n" for e in sorted(excludes))

    try:
        logger.debug("Calling mksquashfs")
        subprocess.check_call(config.c_sudo + [
                                "mksquashfs", "root/", squashfs_fn,
                                "-comp", config.compression,
                                "-ef", exclude_fn])
        if os.getuid() != 0:
            subprocess.check_call(config.c_sudo + [
                                "chown", "{}:{}".format(os.getuid(),
                                                        os.getgid()),
                                                squashfs_fn])
    except:
        if os.path.exists(squashfs_fn):
            os.unlink(squashfs_fn)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
