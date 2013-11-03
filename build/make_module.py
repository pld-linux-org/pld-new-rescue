#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import uuid
from glob import glob

def main():
    parser = argparse.ArgumentParser(description="Make PLD NR image")

    parser.add_argument("module", action="store",
                        help="Module name")
    args = parser.parse_args()

    root_dir = os.path.abspath("root")
    exclude_fn = "{0}.exclude".format(args.module)
    squashfs_fn = "{0}.sqf".format(args.module)
    module_fn = "{0}.cpi".format(args.module)

    if os.path.exists(squashfs_fn):
        os.unlink(squashfs_fn)
    if os.path.exists(module_fn):
        os.unlink(module_fn)

    excludes = set()
    for lst_fn in glob("*.lst"):
        mod_name = lst_fn[:-4]
        if mod_name == args.module:
            continue
        excludes.update(open(lst_fn, "rt").readlines())

    with open(exclude_fn, "wt") as exclude_f:
        exclude_f.writelines(sorted(excludes))

    try:
        subprocess.check_call(["mksquashfs", root_dir, squashfs_fn,
                                "-e", exclude_fn])

        cpio_p = subprocess.Popen(["cpio", "-o", "-H", "newc",
                                    "-F", module_fn],
                                 stdin=subprocess.PIPE)
        cpio_p.stdin.write((squashfs_fn + "\n").encode("utf-8"))
        cpio_p.stdin.close()
        rc = cpio_p.wait()
        if rc:
            raise subprocess.CalledProcessError(rc, ["cpio"])
    except:
        if os.path.exists(module_fn):
            os.unlink(module_fn)
    finally:
        os.unlink(squashfs_fn)

if __name__ == "__main__":
    main()

# vi: sts=4 sw=4 et
