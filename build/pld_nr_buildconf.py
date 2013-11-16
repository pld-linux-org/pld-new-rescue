#!/usr/bin/python3

import os
import sys
import configparser
import subprocess
import logging
import re
import argparse
import shutil
import locale
import crypt
import uuid

from hashlib import md5
from datetime import datetime
from collections import OrderedDict

logger = logging.getLogger()

X86_RE = re.compile("^(i[3-6]86|ia32)$")
X86_64_RE = re.compile("^(x86_64|amd64)$")

HOSTNAME_RE = re.compile("^[a-z0-9][a-z0-9-]{0,63}$")
LOCALE_RE = re.compile("^[a-z]+_[A-Z]+$")

GRUB_VERSION_RE = re.compile(r"\(GRUB\)\s+2\.\d+")
RPM_VERSION_RE = re.compile(r"\(RPM\)\s+5.\d+(.\d+)*")

ARCH_EFI_TO_GRUB = { "ia32": "i386", "x64": "x86_64" }

def _get_default_arch():
    try:
        result = subprocess.check_output(["rpm", "--eval", "%{_arch}"])
        result = result.decode("us-ascii").strip()
    except CalledProcessError:
        return "i486"
    if X86_RE.match(result):
        result = "i486" # make the image compatible with old hardware
    return result

class ConfigError(Exception):
    pass

def _check_tool(tool, description=None, args=["--version"],
                get_output=False, ignore_error=False, quiet=False,
                package=None):
    if isinstance(tool, str):
        tool = [tool]
    if not description:
        description = "command"
        if package:
            description += " (from the '{}' package)".format(package)
    try:
        if quiet:
            stderr = stdout=open("/dev/null", "wb")
        else:
            stderr = None
        if get_output:
            return subprocess.check_output(tool + args, stderr=stderr)
        else:
            subprocess.check_call(tool + args,
                                  stdout=open("/dev/null", "wb"),
                                  stderr=stderr)
    except FileNotFoundError:
        raise ConfigError("{0!r} {1} not found".format(tool[0], description))
    except OSError as err:
        raise ConfigError("{0!r} {1} cannot be executed: {2}"
                                .format(tool[0], description, err))
    except subprocess.CalledProcessError as err:
        if ignore_error:
            return err.output
        raise ConfigError("{0!r} {1} returned {2} exit status"
                        .format(" ".join(tool), description, err.returncode))

def _check_tool_version(command, regexp, package=None):
    ver = _check_tool(command, get_output=True, package=package)
    ver = ver.decode("utf-8", "replace").strip()
    if not regexp.search(ver):
        raise ConfigError("Usupported {0!r} version: {1!r}"
                                                .format(command, ver))

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
        else:
            self.efi_arch = self.efi_arch.lower()
            
        if X86_64_RE.match(self.arch):
            self.bits = 64
        else:
            self.bits = 32

        grub_platforms = self._config.get("grub_platforms")
        if grub_platforms:
            self.grub_platforms = [p.strip() for p in grub_platforms.split(",")]
        else:
            self._choose_grub_platforms()

        self.memtest86 = self._config.getboolean("memtest86", fallback=False)
        self.memtest86_plus = self._config.getboolean("memtest86+",
                                                    fallback=False)

        self.hashed_root_password = self._config.get("hashed_root_password")
        if not self.hashed_root_password:
            root_password = self._config.get("root_password")
            if root_password:
                self.hashed_root_password = crypt.crypt(root_password,
                                                crypt.mksalt(crypt.METHOD_MD5))
            else:
                self.hashed_root_password = ""

        locales = self._config.get("locales")
        if locales.strip():
            self.locales = [l.strip() for l in locales.split(",")]
        else:
            self.locales = ["en_US"]

        self.hostname = self._config.get("hostname", fallback="pld-new-rescue")

        # dummy values
        self.uuid = uuid.UUID("0"*32)
        self.efi_vol_id = "0000-0000"
        self.cd_vol_id = "0000-00-00-00-00-00-00"

        self.load_uuids()

        self.defaults = {k[8:]: v for k, v in self._config.items()
                                                if k.startswith("default_")}

    def load_uuids(self):
        try:
            with open("uuids", "rt") as uuid_f:
                self.uuid = uuid.UUID(uuid_f.readline().strip())
                self.efi_vol_id = uuid_f.readline().strip()
                self.cd_vol_id = uuid_f.readline().strip()
        except IOError as err:
            logger.debug("Cannot load uuids: {}".format(err))

    def gen_uuids(self):
        self.uuid = uuid.uuid4()
        hexdigest = md5(self.uuid.bytes).hexdigest()
        self.efi_vol_id = "{}-{}".format(hexdigest[:4], hexdigest[4:8])
        self.efi_vol_id = self.efi_vol_id.upper()
        timestamp = datetime.now()
        self.cd_vol_id = "{:%Y-%m-%d-%H-%M-%S-%f}".format(timestamp)[:22]
        with open("uuids", "wt") as uuid_f:
            print(str(self.uuid), file=uuid_f)
            print(self.efi_vol_id, file=uuid_f)
            print(self.cd_vol_id, file=uuid_f)

    def _choose_grub_platforms(self):
        self.grub_platforms = []
        if self.bios:
            self.grub_platforms.append("i386-pc")
        if self.efi and self.efi_arch:
            self.grub_platforms.append("{0}-efi".format(
                                        ARCH_EFI_TO_GRUB[self.efi_arch]))

    def verify(self):
        if locale.getpreferredencoding() not in ["UTF-8", "ANSI_X3.4-1968"]:
            raise ConfigError("Non-UTF-8 locales not supported")
        if not X86_RE.match(self.arch) and not X86_64_RE.match(self.arch):
            raise ConfigError("Architecture not supported: {0!r}"
                                                        .format(self.arch))
        for m in self.modules:
            module_dir = os.path.join("../modules", m)
            if not os.path.isdir(module_dir):
                raise ConfigError("Invalid module: '{0}' - there is no '{1}'"
                                    " directory".format(m, module_dir))
        if self.compression not in ("xz", "gzip"):
            raise ConfigError("Unsupported compression: {0!r}"
                                            .format(self.compression))
        if self.compression_level and (
                self.compression_level < 0 or self.compression_level > 9):
            raise ConfigError("Unsupported compression level: {0!r}"
                                            .format(self.compression_level))

        _check_tool(self.compress_cmd, "compress command")

        if self.efi and self.efi_arch not in ("x64", "ia32"):
            raise ConfigError("EFI architecture not supported: {0!r}"
                                                        .format(self.efi_arch))

        _check_tool_version("grub-mkimage", GRUB_VERSION_RE, package="grub2")
        if self.bios:
            _check_tool_version("grub-bios-setup", GRUB_VERSION_RE, package="grub2")
        if self.efi:
            _check_tool_version("grub-mkfont", GRUB_VERSION_RE, package="grub2-mkfont")
            font_fn = "/usr/share/fonts/TTF/DejaVuSansMono.ttf"
            if not os.path.exists(font_fn):
                raise ConfigError("File {!r} (from fonts-TTF-DejaVu package) missing")

        for plat in self.grub_platforms:
            plat_dir = os.path.join("/lib/grub", plat)
            if not os.path.isdir(plat_dir):
                raise ConfigError("Grub platform directory {0!r} not found"
                                                        .format(plat_dir))

        if self.memtest86 and not os.path.exists("/boot/memtest86"):
            raise ConfigError("/boot/memtest86 missing")
        
        if self.memtest86_plus and not os.path.exists("/boot/memtest86+"):
            raise ConfigError("/boot/memtest86+ missing")

        if not HOSTNAME_RE.match(self.hostname):
            raise ConfigError("Bad host name: {0!r}".format(self.hostname))

        for loc in self.locales:
            if not LOCALE_RE.match(loc):
                raise ConfigError("Bad locale name: {!r}".format(loc))

        _check_tool("rpm")
        _check_tool("poldek")
        _check_tool("du")
        _check_tool("dd")
        _check_tool("losetup")
        _check_tool("mkdosfs", ignore_error=True, quiet=True,
                                                        package="dosfstools")
        _check_tool("sfdisk", package="util-linux")
        _check_tool("cpio")
        _check_tool("gen_init_cpio", ignore_error=True, quiet=True,
                                                        package="kernel-tools")
        _check_tool("mksquashfs", args=["-version"], package="squashfs")
        _check_tool("xorriso")

    def get_config_vars(self):
        """Return current config as string->string mapping."""
        result = OrderedDict()
        result["arch"] = self.arch
        result["bits"] = str(self.bits)
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
        result["hashed_root_password"] = self.hashed_root_password
        result["memtest86"] = "yes" if self.memtest86 else "no"
        result["memtest86+"] = "yes" if self.memtest86_plus else "no"
        result["hostname"] = self.hostname
        result["locales"] = ",".join(self.locales)
        result["uuid"] = str(self.uuid)
        result["efi_vol_id"] = self.efi_vol_id
        result["cd_vol_id"] = self.cd_vol_id
        for k, v in self.defaults.items():
            result["default_" + k] = v
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
        old_pwd = os.getcwd()
        os.chdir(source)
        try:
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
        finally:
            os.chdir(old_pwd)

    def copy_template_dir(self, source, dest):
        return self.copy_dir(source, dest, True)

    def run_script(self, script):
        env = {"pldnr_" + k: v for k, v in self.get_config_vars().items()}
        env["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin"
        subprocess.check_call(["/bin/sh", "-ex", script], env=env)

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
        lines.append("EFI_GRUB_PLATFORMS={0}".format(
                            " ".join(p for p in self.grub_platforms
                                            if p.endswith("-efi"))))
        lines.append("PC_GRUB_PLATFORMS={0}".format(
                            " ".join(p for p in self.grub_platforms
                                            if p.endswith("-pc"))))
        lines.append("EFI_GRUB_IMAGES={0}".format(
                            " ".join("grub-{}.img".format(p)
                                            for p in self.grub_platforms
                                            if p.endswith("-efi"))))
        if self.bios  and "i386-pc" in self.grub_platforms:
            lines.append("PC_GRUB_IMAGES=cdboot.img hdboot.img")
        else:
            lines.append("PC_GRUB_IMAGES=")
        lines.append("COMPRESS={0}".format(" ".join(self.compress_cmd)))
        lines.append("VERSION={0}".format(self.version))
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
    parser.add_argument("--verify",
                        action="store_true",
                        help="Verify config and requirements")
    parser.add_argument("--gen-uuids",
                        action="store_true",
                        help="Generate new UUIDs for build")
    parser.set_defaults(mode="dump")
    args = parser.parse_args()
    setup_logging(args)
    config = Config.get_config()
    if args.gen_uuids:
        config.gen_uuids()
    if args.verify:
        config.verify()
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
    try:
        main()
    except (subprocess.CalledProcessError, ConfigError) as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sw=4 sts=4 et
