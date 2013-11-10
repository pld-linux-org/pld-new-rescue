#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import logging
from io import SEEK_CUR

from hashlib import md5

import pld_nr_buildconf

logger = logging.getLogger()

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Make boot CD image",
                                     parents=[log_parser])
    parser.add_argument("source",
                        help="PLD NR boot image")
    parser.add_argument("destination",
                        help="Destination ISO file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    iso_img_dir = os.path.abspath("../iso_img")
    tmp_img_dir = os.path.abspath("iso_img")
    
    grub_early_fn = "grub_early_iso.cfg"
    grub_img_fn = os.path.join(tmp_img_dir, "eltorito-grub.img")

    with open(grub_early_fn, "wt") as grub_early:
        grub_early.write("search.fs_uuid {} cd\n"
                         "loopback loop ($cd)/pld-nr-{}.img\n"
                         "set root=(loop,msdos1)\n"
                         "set prefix=($root)/grub\n"
                         .format(config.cd_vol_id, config.bits))

    if not os.path.isdir(tmp_img_dir):
        os.makedirs(tmp_img_dir)
    try:
        logger.debug("Building GRUB boot image")
        grub_core_modules = ["search", "search_label", "fat", "part_msdos",
                                "biosdisk", "loopback", "iso9660"]
        subprocess.check_call(["grub-mkimage",
                                "--output", "iso-grub.img",
                                "--format", "i386-pc",
                                "--prefix", "/grub",
                                "--config", grub_early_fn,
                                ] + grub_core_modules)
        with open(grub_img_fn, "wb") as grub_img_f:
            with open("/lib/grub/i386-pc/cdboot.img", "rb") as cdboot_f:
                grub_img_f.write(cdboot_f.read())
            with open("iso-grub.img", "rb") as iso_grub_f:
                grub_img_f.write(iso_grub_f.read())

        logger.debug("Copying CD contents template")
        config.copy_template_dir(iso_img_dir, tmp_img_dir)

        logger.debug("Creating the ISO image")
        command = ["mkisofs",
                "-verbose",
                "-joliet",
                "-jcharset", "utf-8",
                "-rock",
                "-appid", "PLD New Rescue",
                "-volid", "PLD NR {}".format(config.version)[:32],
                "-boot-info-table",
                "-eltorito-catalog", "boot.catalog",
                ]

        if config.bios:
            command += [
                      "-no-emul-boot",
                      "-boot-load-size", "4",
                      "-eltorito-boot", "eltorito-grub.img",
                      ]
            if config.efi:
                command += ["-eltorito-alt-boot"]
        if config.efi:
            command += [
                      "-hard-disk-boot",
                      "-efi-boot", os.path.basename(args.source),
                      ]
        command += [
                "-preparer", "https://github.com/Jajcus/pld-new-rescue",
                #"-log-file", "mkisofs.log",
                "-o", args.destination,
                "-graft-points",
                "{}={}".format(os.path.basename(args.source), args.source),
                tmp_img_dir,
                ]
        subprocess.check_call(command)

        logger.debug("Updating the image creation date ('UUID')")
        with open(args.destination, "br+", buffering=0) as img_f:
            logger.debug("    seeking to sector 16")
            img_f.seek(16 * 2048)
            buf = bytearray(2048)
            while True:
                length = img_f.readinto(buf)
                logger.debug("    {} bytes read".format(length))
                if buf[1:6] != b"CD001":
                    raise RuntimeError("Primary Volume Descriptor not found")
                d_type = buf[0]
                logger.debug("    Volume Descriptor type {} found"
                                                            .format(d_type))
                if d_type == 1:
                    break
            if length != 2048:
                raise RuntimeError("Primary Volume Descriptor too short")
            buf[813:829] = config.cd_vol_id.replace("-", "").encode("ascii")
            buf[829] = 0
            buf[830:847] = buf[813:830]
            img_f.seek(-2048, SEEK_CUR)
            img_f.write(buf)
    finally:
        shutil.rmtree(tmp_img_dir)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
