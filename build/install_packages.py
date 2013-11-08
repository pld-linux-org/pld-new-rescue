#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import logging

import pld_nr_buildconf

logger = logging.getLogger()

class PackageInstaller(object):
    def __init__(self, config):
        self.config = config
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
                                "--conf", "poldek.conf",
                                "--cachedir", self.cache_dir]
                                + list(args))
    def setup_chroot(self):
        dev_dir = os.path.join(self.dst_dir, "dev")
        subprocess.check_call(["mount", "--bind", "/dev", dev_dir])
        dev_pts_dir = os.path.join(dev_dir, "pts")
        if not os.path.isdir(dev_pts_dir):
            os.makedirs(dev_pts_dir)
        subprocess.check_call(["mount", "-t", "devpts", 
                               "-o", "gid=5,mode=620",
                               "none", dev_pts_dir])
        proc_dir = os.path.join(self.dst_dir, "proc")
        subprocess.check_call(["mount", "-t", "proc", "none", proc_dir])
        sys_dir = os.path.join(self.dst_dir, "sys")
        subprocess.check_call(["mount", "-t", "sysfs", "none", sys_dir])

    def get_file_list(self):
        result = []
        old_dir = os.getcwd()
        os.chdir(self.dst_dir)
        try:
            for dirpath, dirnames, filenames in os.walk("."):
                dirpath = dirpath[2:] # strip "./"
                if not dirpath:
                    dirnames[:] = [d for d in dirnames 
                                    if d not in ["dev", "proc", "sys", "tmp"]]
                elif dirpath == "var":
                    dirnames[:] = [d for d in dirnames if d not in ["tmp"]]
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
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Install packages",
                                     parents=[log_parser])
    parser.add_argument("--no-clean", action="store_true",
                        help="Do not clean up after failed install")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)

    config = pld_nr_buildconf.Config.get_config()

    installer = PackageInstaller(config)
    try:
        installer.init_rpm_db()
        installer.poldek("--upa")
        prev_files = set()
        installer.poldek("--install", "filesystem")
        installer.setup_chroot()
        for module in config.modules:
            if module == "base":
                lst_fn = "base.full-lst"
            else:
                lst_fn = "{0}.lst".format(module)
            logger.debug("Checking if {0!r} already exists".format(lst_fn))
            if os.path.exists(lst_fn):
                files = [l.strip() for l in open(lst_fn, "rt").readlines()]
                prev_files.update(files)
                logger.info("'{0}' packages already installed".format(module))
                open(lst_fn, "a").close() # update mtime
                continue
            pset_fn = "../modules/{0}/conds_workaround.pset".format(module)
            if os.path.exists(pset_fn):
                logger.debug("Installing conds_workaround packages for {0}"
                                    .format(module))
                installer.poldek("--install", "--pset", pset_fn,
                            "--nofollow", "--nodeps", "--pmopt", "noscripts")
            pset_fn = "../modules/{0}/packages.pset".format(module)
            if os.path.exists(pset_fn):
                logger.debug("Installing packages for {0}".format(module))
                installer.poldek("--install", "--pset", pset_fn)
            logger.debug("Getting list of installed files")
            files = set(installer.get_file_list())
            module_files = files - prev_files
            prev_files = files
            logger.debug("Writing {0!r}".format(lst_fn))
            with open(lst_fn, "wt") as lst_f:
                for path in sorted(module_files):
                    print(path, file=lst_f)
    except:
        if not args.no_clean:
            installer.cleanup(True)
        raise
    else:
        installer.cleanup(False)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))

# vi: sts=4 sw=4 et
