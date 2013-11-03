#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil

class PackageInstaller(object):
    def __init__(self):
        self.dst_dir = os.path.abspath("root")
        self.cache_dir = os.path.abspath("cache")
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)
    def init_rpm_db(self):
        if not os.path.isdir(self.dst_dir):
            os.makedirs(self.dst_dir)
        packages_db = os.path.join(self.dst_dir, "var/lib/rpm/Packages")
        if not os.path.exists(packages_db):
            subprocess.check_call(["rpm", "--initdb", "--root", self.dst_dir])
    def poldek(self, *args):
        subprocess.check_call(["poldek", "--root", self.dst_dir,
                                "--conf", "../packages/poldek.conf",
                                "--cachedir", self.cache_dir]
                                + list(args))
    def setup_chroot(self):
        dev_dir = os.path.join(self.dst_dir, "dev")
        subprocess.check_call(["mount", "--bind", "/dev", dev_dir])
        dev_pts_dir = os.path.join(dev_dir, "pts")
        if not os.path.isdir(dev_pts_dir):
            os.makedirs(dev_pts_dir)
        subprocess.check_call(["mount", "-t", "devpts", "none", dev_pts_dir])
        proc_dir = os.path.join(self.dst_dir, "proc")
        subprocess.check_call(["mount", "-t", "proc", "none", proc_dir])
        sys_dir = os.path.join(self.dst_dir, "sys")
        subprocess.check_call(["mount", "-t", "sys", "none", sys_dir])

    def get_file_list(self):
        result = []
        old_dir = os.getcwd()
        os.chdir(self.dst_dir)
        try:
            for dirpath, dirnames, filenames in os.walk("."):
                dirpath = dirpath[2:] # strip "./"
                if not dirpath:
                    dirnames = [d for d in dirnames 
                                    if d not in ["dev", "proc", "sys", "tmp"]]
                elif dirpath == "var":
                    dirnames = [d for d in dirnames if d not in ["tmp"]]
                for dirname in dirnames:
                    result.append(os.path.join(dirpath, dirname))
                for filename in filenames:
                    result.append(os.path.join(dirpath, filename))
        finally:
            os.chdir(old_dir)
        return result

    def cleanup(self, total=False):
        dev_dir = os.path.join(self.dst_dir, "dev")
        dev_pts_dir = os.path.join(dev_dir, "pts")
        proc_dir = os.path.join(self.dst_dir, "proc")
        sys_dir = os.path.join(self.dst_dir, "sys")
        subprocess.call(["umount", sys_dir])
        subprocess.call(["umount", proc_dir])
        subprocess.call(["umount", dev_pts_dir])
        subprocess.call(["umount", dev_dir])
        if total and os.path.isdir(self.dst_dir):
            shutil.rmtree(self.dst_dir)

def main():
    parser = argparse.ArgumentParser(description="Install packages")
    parser.add_argument("--no-clean", action="store_true",
                        help="Do not clean up after failed install")
    parser.add_argument("pset", nargs="*",
                        help="Package set to install")
    args = parser.parse_args()

    installer = PackageInstaller()
    try:
        installer.init_rpm_db()
        installer.poldek("--upa")
        installer.poldek("--install", 
                            "--pset", "../packages/conds_workaround.pset",
                            "--nofollow", "--nodeps", "--pmopt", "noscripts")
        installer.poldek("--install",
                                "--pset", "../packages/base.pset")
        base_files = installer.get_file_list()
        with open("base.lst", "wt") as base_lst:
            for path in base_files:
                print(path, file=base_lst)
    except:
        if not args.no_clean:
            installer.cleanup(True)
        raise
    else:
        installer.cleanup(False)

if __name__ == "__main__":
    main()

# vi: sts=4 sw=4 et
