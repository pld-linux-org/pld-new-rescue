#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import logging
import tempfile

import pld_nr_buildconf

logger = logging.getLogger("make_grub_img")

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Make boot image",
                                     parents=[log_parser])
    parser.add_argument("platform",
                        default="i386-pc", 
                        help="Grub platform name")
    parser.add_argument("destination",
                        help="Destination file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    with tempfile.NamedTemporaryFile(mode="w+t") as grub_early:
        grub_early.write("""
echo "starting grub ({platform})"
search.fs_uuid {vol_id} root
search.fs_uuid {efi_id} efi_part
set prefix=($root)/boot/grub
echo "using prefix: $prefix efi_part: $efi_part"
"""
                     .format(platform=args.platform,
                             vol_id=config.cd_vol_id,
                             efi_id=config.efi_vol_id))
        grub_early.flush()
        grub_core_modules = ["minicmd"]
        if args.platform.endswith("-pc"):
            grub_core_modules += ["biosdisk"]
        grub_core_modules += ["iso9660", "search", "search_label", "fat",
                            "part_gpt", "echo", "iso9660", "minicmd"]
        logger.debug("Making {} grub image for {} with modules: {!r}"
                        .format(args.destination, args.platform,
                                                    grub_core_modules))
        subprocess.check_call(["grub-mkimage",
                                "--output", args.destination,
                                "--format", args.platform,
                                "--prefix", "/boot/grub",
                                "--config", grub_early.name,
                                ] + grub_core_modules)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
