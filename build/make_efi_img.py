#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import logging

from hashlib import md5

import pld_nr_buildconf

logger = logging.getLogger("make_efi_img")

DU_OUTPUT_RE = re.compile("^(\d+)\s+total", re.MULTILINE)

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Make EFI partition image",
                                     parents=[log_parser])
    parser.add_argument("destination",
                        nargs="?",
                        default="efi.img",
                        help="Destination file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    efi_img_fn = os.path.abspath(args.destination)
    efi_templ_dir = os.path.abspath("../efi_templ")
    efi_mnt_dir = os.path.abspath("efi_mnt")

    grub_files = {}
    for plat in config.grub_platforms:
        if not plat.endswith("-efi"):
            continue
        img_fn = os.path.abspath("grub-{}.img".format(plat))
        if plat.startswith("i386-"):
            grub_files[img_fn] = "IA32"
        elif plat.startswith("x86_64"):
            grub_files[img_fn] = "X64"
        else:
            logger.warning("Unuspported GRUB EFI platform: {}".format(plat))

    logger.info("Computing required image size")
    extra_files = list(grub_files)

    if config.efi_shell:
        efi_shell_path = "/lib/efi/{}/Shell.efi".format(config.efi_arch)
        extra_files.append(efi_shell_path)

    du_output = subprocess.check_output(["du", "-sbcD",
                                            "../efi_templ",
                                            ] + extra_files)
    match = DU_OUTPUT_RE.search(du_output.decode("utf-8"))
    bytes_needed = int(int(match.group(1)) * 1.2)
    logger.debug("bytes needed: {0!r}".format(bytes_needed))
    blocks_needed = max(bytes_needed // 1024, 256)

    logger.info("Creating the image")
    subprocess.check_call(["dd", "if=/dev/zero", "of=" + efi_img_fn,
                            "bs=1024", "count={0}".format(blocks_needed)])
    try:
        subprocess.check_call(["mkdosfs", "-I",
                                "-i", config.efi_vol_id.replace("-", ""),
                                efi_img_fn])
        if not os.path.exists(efi_mnt_dir):
            os.makedirs(efi_mnt_dir)
        subprocess.check_call(["mount", "-t", "vfat",
                                "-o", "utf8=true,loop",
                                efi_img_fn, efi_mnt_dir])
        try:
            logger.info("Installing PLD NR EFI files")
            efi_boot_dir = os.path.join(efi_mnt_dir, "EFI/BOOT")
            os.makedirs(efi_boot_dir)
            if config.efi_shell:
                shutil.copy(efi_shell_path, os.path.join(efi_mnt_dir, "EFI",
                                "SHELL{}.EFI".format(config.efi_arch.upper())))
            config.copy_template_dir(efi_templ_dir, efi_mnt_dir)
            for source, efi_arch in grub_files.items():
                dst = os.path.join(efi_boot_dir, "BOOT{}.EFI".format(efi_arch))
                shutil.copy(source, dst)
        finally:
            subprocess.call(["umount", efi_mnt_dir])
    except:
        os.unlink(efi_img_fn)
        raise

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
