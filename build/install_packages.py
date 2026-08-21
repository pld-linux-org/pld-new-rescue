#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import logging

from glob import glob

import pld_nr_buildconf

logger = logging.getLogger("install_packages")

class PackageInstaller(object):
    def __init__(self, config):
        self.config = config
        self.dst_dir = os.path.abspath("root")
        self.cache_dir = os.path.abspath("cache")
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)
        if config.locales:
            langs = set(config.locales)
            langs.add("C")
            for loc in config.locales:
                if "_" in loc:
                    langs.add(loc.split("_", 1)[0])
            self.langs_opts = ["-O", "rpmdef=_install_langs {}"
                                            .format(":".join(langs))]
        else:
            self.langs_opts = []

    def init_minimal_dev(self):
        dev_dir = os.path.join(self.dst_dir, "dev")
        os.makedirs(dev_dir, exist_ok=True)

        devices = [
            ("null",    "666", "c", 1, 3),
            ("zero",    "666", "c", 1, 5),
            ("full",    "666", "c", 1, 7),
            ("random",  "666", "c", 1, 8),
            ("urandom", "666", "c", 1, 9),
            ("console", "600", "c", 5, 1),
        ]

        for name, mode, dev_type, maj, minr in devices:
            path = os.path.join(dev_dir, name)
            subprocess.check_call(self.config.c_sudo + ["/bin/mknod", "-m", mode, path, dev_type, str(maj), str(minr)])

    def init_rpm_db(self):
        if not os.path.isdir(self.dst_dir):
            os.makedirs(self.dst_dir)
        packages_db = os.path.join(self.dst_dir, "var/lib/rpm/Packages")
        if not os.path.exists(packages_db):
            subprocess.check_call(self.config.c_sudo + 
                                    ["rpm", "--initdb", "--root", self.dst_dir])
    def import_rpm_keys(self):
        # rpm verifies against the target rpmdb, and the key file itself only
        # arrives with the 'rpm' package in 'basic' - a whole module too late
        keys = sorted(glob("/etc/pki/rpm-gpg/*.asc"))
        if not keys:
            logger.error("No RPM signing keys in /etc/pki/rpm-gpg,"
                            " cannot verify package signatures")
            sys.exit(1)
        logger.info("Trusting package signatures from: {0}"
                        .format(", ".join(os.path.basename(k) for k in keys)))
        subprocess.check_call(self.config.c_sudo
                                + ["rpm", "--root", self.dst_dir, "--import"]
                                + keys)

    def poldek(self, *args, ignore_errors=False):
        try:
            cmd = self.config.c_sudo \
                                + ["poldek", "--root", self.dst_dir,
                                "--conf", "poldek.conf",
                                "--cachedir", self.cache_dir,
                                "-O", "rpmdef=_netsharedpath ''" ] \
                                + self.langs_opts + list(args)
            logger.debug("Running: {0}".format(cmd))
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            if not ignore_errors:
                raise
    def setup_chroot(self):
        dev_dir = os.path.join(self.dst_dir, "dev")
        subprocess.check_call(self.config.c_sudo + [
                                        "mount", "--bind", "/dev", dev_dir])
        dev_pts_dir = os.path.join(dev_dir, "pts")
        if not os.path.isdir(dev_pts_dir):
            os.makedirs(dev_pts_dir)
        subprocess.check_call(self.config.c_sudo + [
                                    "mount", "-t", "devpts", 
                                    "-o", "gid=5,mode=620",
                                    "none", dev_pts_dir])
        proc_dir = os.path.join(self.dst_dir, "proc")
        subprocess.check_call(self.config.c_sudo + [
                                "mount", "-t", "proc", "none", proc_dir])
        sys_dir = os.path.join(self.dst_dir, "sys")
        subprocess.check_call(self.config.c_sudo + [
                                "mount", "-t", "sysfs", "none", sys_dir])

    def get_file_list(self):
        result = []
        old_dir = os.getcwd()
        os.chdir(self.dst_dir)
        try:
            paths = subprocess.check_output(
                                        self.config.c_sudo + [
                                            "find", ".",
                                            "-ignore_readdir_race",
                                            "(",
                                            "-path", "./dev",
                                            "-o", "-path", "./proc",
                                            "-o", "-path", "./sys",
                                            "-o", "-path", "./tmp",
                                            "-o", "-path", "./var/tmp",
                                            ")",
                                            "-prune", "-o", "-print0"])
            for path in paths.split(b"\000"):
                path = path[2:] # strip "./"
                if not path:
                    continue
                result.append(path.decode("utf-8"))
        finally:
            os.chdir(old_dir)
        return result

    def get_installed_pkg_list(self):
        cmd = self.config.c_sudo + ["rpm", "--root", self.dst_dir, "-qa",
                                                "--queryformat", "%{name}\n"]
        pkg_list = subprocess.check_output(cmd)
        pkg_list = pkg_list.decode("utf-8").strip().split("\n")
        logger.debug("Installed packages: {!r}".format(pkg_list))
        return pkg_list

    def get_installed_pkg_info(self):
        cmd = self.config.c_sudo + ["rpm", "--root", self.dst_dir, "-qa",
            "--queryformat", "%{name}\t%{version}-%{release}\t%{size}\t%{summary}\n"]
        result = []
        rpm_p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        for line in rpm_p.stdout:
            line = line.decode("utf-8").strip()
            if not line:
                continue
            pkg, version, size, summary = line.split("\t", 3)
            result.append((pkg, version, int(size), summary))
        return result

    def cleanup(self, total=False):
        dev_dir = os.path.join(self.dst_dir, "dev")
        dev_pts_dir = os.path.join(dev_dir, "pts")
        proc_dir = os.path.join(self.dst_dir, "proc")
        sys_dir = os.path.join(self.dst_dir, "sys")
        subprocess.call(self.config.c_sudo + ["umount", sys_dir])
        subprocess.call(self.config.c_sudo + ["umount", proc_dir])
        subprocess.call(self.config.c_sudo + ["umount", dev_pts_dir])
        subprocess.call(self.config.c_sudo + ["umount", dev_dir])
        if total and os.path.isdir(self.dst_dir):
            if self.config.c_sudo:
                subprocess.call(self.config.c_sudo + [
                                        "rm", "-rf", self.dst_dir])
            else:
                shutil.rmtree(self.dst_dir)

def format_size(size):
    if size >= 1024 * 1024:
        return "{:.1f}M".format(size / (1024 * 1024))
    elif size >= 1024:
        return "{:.0f}K".format(size / 1024)
    else:
        return "{}B".format(size)

def write_package_list(filename, installer, modules, package_modules):
    packages_info = installer.get_installed_pkg_info()
    name_width = max(len(p[0]) for p in packages_info)
    ver_width = max(len(p[1]) for p in packages_info)
    size_width = max(len(format_size(p[2])) for p in packages_info)
    sum_width = max(len(p[3]) for p in packages_info)
    module_width = max(len(m) for m in modules)
    with open(filename, "wt") as pkg_lst_file:
        print("{:<{}} {:<{}} {:>{}} {:<{}} {}"
                    .format("name", name_width,
                            "version", ver_width,
                            "size", size_width,
                            "module", module_width,
                            "summary"), file=pkg_lst_file)
        print("{} {} {} {} {}"
                    .format("-" * name_width,
                            "-" * ver_width,
                            "-" * size_width,
                            "-" * module_width,
                            "-" * sum_width), file=pkg_lst_file)
        for pkg_name, pkg_ver, pkg_size, pkg_sum in sorted(packages_info):
            module = package_modules.get(pkg_name, "?")
            print("{:<{}} {:<{}} {:>{}} {:<{}} {}"
                        .format(pkg_name, name_width,
                                pkg_ver, ver_width,
                                format_size(pkg_size), size_width,
                                module, module_width,
                                pkg_sum), file=pkg_lst_file)

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Install packages",
                                     parents=[log_parser])
    parser.add_argument("--no-clean", action="store_true",
                        help="Do not clean up after failed install")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)

    config = pld_nr_buildconf.Config.get_config()

    lst_files = []

    installer = PackageInstaller(config)
    try:
        installer.init_minimal_dev()
        installer.init_rpm_db()
        installer.import_rpm_keys()
        installer.poldek("--upa", ignore_errors=True)
        prev_files = set()
        installer.poldek("--install", "filesystem")
        installer.setup_chroot()
        # packages needed early, before main rpm transaction
        installer.poldek("--install", "mksh")
        package_modules = {}
        def record_module_packages(module, installed_now):
            # rpm only knows what is installed now, not which module brought it
            # in, so each module's share is snapshotted next to its file list
            pkgs_fn = "{0}.pkgs".format(module)
            lst_files.append(pkgs_fn)
            if installed_now:
                pkgs = [pkg for pkg in installer.get_installed_pkg_list()
                                            if pkg not in package_modules]
                with open(pkgs_fn, "wt") as pkgs_f:
                    for pkg in sorted(pkgs):
                        print(pkg, file=pkgs_f)
            elif os.path.exists(pkgs_fn):
                pkgs = [l.strip() for l in open(pkgs_fn, "rt").readlines()
                                                                if l.strip()]
            else:
                # tree built before the snapshots existed
                logger.warning("No {0!r}, cannot tell which packages '{1}'"
                                " installed".format(pkgs_fn, module))
                return
            for pkg in pkgs:
                package_modules.setdefault(pkg, module)
        for module in config.modules:
            if module == "base":
                lst_fn = "base.full-lst"
            else:
                lst_fn = "{0}.lst".format(module)
            lst_files.append(lst_fn)
            logger.debug("Checking if {0!r} already exists".format(lst_fn))
            if os.path.exists(lst_fn):
                files = [l.strip() for l in open(lst_fn, "rt").readlines()]
                prev_files.update(files)
                logger.info("'{0}' packages already installed".format(module))
                open(lst_fn, "a").close() # update mtime
                record_module_packages(module, False)
                continue
            script_fn = "../modules/{0}/pre-install.sh".format(module)
            if os.path.exists(script_fn):
                config.run_script(script_fn, sudo=True)
            pset_fn = "../modules/{0}/deps_workaround.pset".format(module)
            if os.path.exists(pset_fn):
                logger.debug("Installing deps_workaround packages for {0}"
                                    .format(module))
                installer.poldek("--install", "--pset", pset_fn,
                            "--nofollow", "--nodeps", "--pmopt", "noscripts")
            pset_fn = "../modules/{0}/packages.pset".format(module)
            if os.path.exists(pset_fn):
                logger.debug("Installing packages for {0}".format(module))
                installer.poldek("--install", "--pset", pset_fn)
            script_fn = "../modules/{0}/post-install.sh".format(module)
            if os.path.exists(script_fn):
                logger.debug("Running the 'post-install' script")
                config.run_script(script_fn, sudo=True)
            logger.debug("Getting list of installed files")
            files = set(installer.get_file_list())
            module_files = files - prev_files
            prev_files = files
            logger.debug("Writing {0!r}".format(lst_fn))
            with open(lst_fn, "wt") as lst_f:
                for path in sorted(module_files):
                    print(path, file=lst_f)
            record_module_packages(module, True)
        write_package_list("../pld-nr-{}.packages".format(config.bits),
                            installer, config.modules, package_modules)
    except:
        if not args.no_clean:
            installer.cleanup(True)
            for lst_fn in lst_files:
                if os.path.exists(lst_fn):
                    try:
                        os.unlink(lst_fn)
                    except OSError as err:
                        logger.warning(str(err))
        raise
    else:
        installer.cleanup(False)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
