#!/usr/bin/python3

import os
import sys
import configparser
import subprocess
import logging
import re
import argparse
import shutil

from collections import OrderedDict

logger = logging.getLogger()

X86_RE = re.compile("^(i[3-6]86|ia32)$")
X86_64_RE = re.compile("^(x86_64|amd64)$")

ARCH_EFI_TO_GRUB = { "ia32": "i386", "x64": "x86_64" }

def _get_default_arch():
    try:
        result = subprocess.check_output(["rpm", "--eval", "%{_arch}"])
        result = result.decode("us-ascii").strip()
    except CalledProcessError:
        return "i686"
    return result

class ConfigError(Exception):
    pass

class Config(object):
    _instance = None
    def __init__(self, filename, build_dir=None):
        self._parsed = configparser.ConfigParser()
        try:
            self._parsed.read(filename)
        except configparser.Error as err:
            raise ConfigError("Could not load the {0!r} file: {1}"
                                                .format(filename, err))
        try:
            self._config = self._parsed["config"]
        except KeyError:
            raise ConfigError("No [config] section in build.conf")
        if build_dir is None:
            build_dir = os.path.join(os.path.dirname(filename), "build")
        self.build_dir = build_dir

        if os.path.isdir("../.git"):
            version = subprocess.check_output(["git", "describe", "--dirty"])
            self.version = version.decode("utf-8").strip()
        else:
            self.version = self._config.get("version", fallback="unknown")

        self.arch = self._config.get("arch")
        if not self.arch:
            self.arch = _get_default_arch()

        modules = self._config.get("modules", "base,basic")
        self.modules = [m.strip() for m in modules.split(",")]
        self.module_files = [m + ".cpi" for m in self.modules]
        self.module_sqf_files = [m + ".sqf" for m in self.modules]
        self.module_lst_files = [m + ".lst" for m in self.modules]
        
        self.compression = self._config.get("compression", fallback="xz")
        self.compress_cmd = [self.compression]
        if self.compression == "xz":
            self.compress_cmd += ["--check=crc32"]

        if self.compression == "gzip":
            self.compressed_ext = ".gz"
        else:
            self.compressed_ext = ".{0}".format(self.compression)
        self.compression_level =  self._config.get("compression_level",
                                                   fallback=None)
        if self.compression_level:
            self.compression_level = int(self.compression_level)
            self.compress_cmd.append("-{0}".format(self.compression_level))

        self.efi = self._config.getboolean("efi", fallback=False)
        self.bios = self._config.getboolean("bios", fallback=True)

        self.efi_arch = self._config.get("efi_arch")
        if not self.efi_arch:
            if X86_64_RE.match(self.arch):
                self.efi_arch = "x64"
            elif X86_RE.match(self.arch):
                self.efi_arch = "ia32"
            else:
                self.efi_arch = None
            
        if X86_64_RE.match(self.arch):
            self.bits = 64
        else:
            self.bits = 32

        grub_platforms = self._config.get("grub_platforms")
        if grub_platforms:
            self.grub_platforms = [p.strip() for p in grub_platforms.split(",")]
        else:
            self._choose_grub_platforms()

    def _choose_grub_platforms(self):
        self.grub_platforms = []
        if self.bios:
            self.grub_platforms.append("i386-pc")
        if self.efi and self.efi_arch:
            self.grub_platforms.append("{0}-efi".format(
                                        ARCH_EFI_TO_GRUB[self.efi_arch]))

    def get_config_vars(self):
        """Return current config as string->string mapping."""
        result = OrderedDict()
        result["arch"] = self.arch
        result["modules"] = ",".join(self.modules)
        result["compression"] = self.compression
        if self.compression_level is not None:
            result["compression_level"] = self.compression_level
        result["efi"] = "yes" if self.efi else "no"
        result["bios"] = "yes" if self.bios else "no"
        if self.efi:
            result["efi_arch"] = self.efi_arch
        else:
            result["efi_arch"] = ""
        result["grub_platforms"] = ",".join(self.grub_platforms)
        result["version"] = self.version
        return result

    def substitute_bytes(self, data):
        """Copy `source` file to `dest` substituting @var@ strings."""
        config_vars = self.get_config_vars()
        def repl(match):
            key = match.group(1)
            try:
                key = key.decode("utf-8")
                return config_vars[key].encode("utf-8")
            except (KeyError, ValueError, UnicodeError):
                return match.group(0)
        SUB_RE = re.compile(b"@(\w+)@")
        data = SUB_RE.sub(repl, data)
        return data
    
    def copy_substituting(self, source, dest):
        """Copy `source` file to `dest` substituting @var@ strings."""
        with open(source, "rb") as source_f:
            data = source_f.read()
            data = self.substitute_bytes(data)
            with open(dest, "wb") as dest_f:
                dest_f.write(data)

    def copy_dir(self, source, dest, substitution=False):
        os.chdir(source)
        for dirpath, dirnames, filenames in os.walk("."):
            dirpath = dirpath[2:] # strip "./"
            for dirname in dirnames:
                path = os.path.join(dirpath, dirname)
                dst_path = os.path.join(dest, path)
                if not os.path.exists(dst_path):
                    os.makedirs(dst_path)
            for filename in filenames:
                if filename.endswith("~"):
                    continue
                path = os.path.join(dirpath, filename)
                dst_path = os.path.join(dest, path)
                if substitution and filename.endswith(".pldnrt"):
                    dst_path = dst_path[:-7]
                    self.copy_substituting(path, dst_path)
                else:
                    shutil.copy(path, dst_path)

    def copy_template_dir(self, source, dest):
        return self.copy_dir(source, dest, True)

    def __str__(self):
        return "[config]\n{0}\n".format(
                    "\n".join("{0}={1}".format(k, v)
                                    for k,v in self.get_config_vars().items()))

    def build_make_vars(self):
        lines = []
        lines.append("ARCH={0}".format(self.arch))
        lines.append("BITS={0}".format(self.bits))
        lines.append("MODULES={0}".format(" ".join(self.modules)))
        lines.append("MODULE_FILES={0}".format(" ".join(self.module_files)))
        lines.append("MODULE_SQF_FILES={0}".format(
                                            " ".join(self.module_sqf_files)))
        lines.append("MODULE_LST_FILES={0}".format(
                                            " ".join(self.module_lst_files)))
        lines.append("PSET_LST_FILES=base.full-lst {0}".format(
                        " ".join(f for f in self.module_lst_files
                                                        if f != "base.lst")))
        lines.append("EFI={0}".format("yes" if self.efi else "no"))
        lines.append("BIOS={0}".format("yes" if self.bios else "no"))
        lines.append("EFI_ARCH={0}".format(self.efi_arch if self.efi else ""))
        lines.append("GRUB_PLATFORMS={0}".format(" ".join(self.grub_platforms)))

        lines.append("COMPRESS={0}".format(" ".join(self.compress_cmd)))
        return "\n".join(lines)

    def build_make_deps(self):
        lines = []
        lines.append("")
        for m in self.modules:
            lines.append("{0}.cpi: {0}.sqf".format(m))
            lines.append(".INTERMEDIATE: {0}.sqf".format(m))
            lines.append("{0}.sqf: root/var/lib/rpm/Packages\n".format(m))
        lines.append(".SECONDARY: base.full-lst")
        return "\n".join(lines)

    @classmethod
    def get_config(cls):
        if cls._instance:
            return _instance
        build_dir = os.path.dirname(__file__)
        filename = os.path.join(build_dir, "../build.conf")
        cls._instance = cls(os.path.abspath(filename),
                            os.path.abspath(build_dir))
        return cls._instance

def get_logging_args_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug",
                        dest='log_level',
                        action='store_const',
                        const=logging.DEBUG,
                        default=logging.INFO,
                        help="Enable extra logging")
    return parser

def setup_logging(args):
    logging.basicConfig(level=args.log_level)
    
def main():
    log_parser = get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Process PLD NR build config",
                                     parents=[log_parser])
    parser.add_argument("--make-vars",
                        dest="mode",
                        action="store_const",
                        const="make_vars",
                        help="Generate make variables")
    parser.add_argument("--make-deps",
                        dest="mode",
                        action="store_const",
                        const="make_deps",
                        help="Generate make dependencies")
    parser.add_argument("--substitute",
                        dest="mode",
                        action="store_const",
                        const="sub",
                        help="Substitute @variables@ in stdin.")
    parser.set_defaults(mode="dump")
    args = parser.parse_args()
    setup_logging(args)
    config = Config.get_config()
    if args.mode == "dump":
        print(config)
    elif args.mode == "make_vars":
        print(config.build_make_vars())
        print("MAKE_VARS_INCLUDED=yes")
    elif args.mode == "make_deps":
        print(config.build_make_deps())
    elif args.mode == "sub":
        sys.stdin = sys.stdin.detach()
        sys.stdout = sys.stdout.detach()
        data = sys.stdin.read()
        sys.stdout.write(config.substitute_bytes(data))

if __name__ == "__main__":
    main()

# vi: sw=4 sts=4 et
