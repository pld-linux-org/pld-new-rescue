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
    parser.add_argument("--pxe", action="store_true",
                        help="Build image for PXE boot")
    parser.add_argument("destination",
                        help="Destination file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    if args.platform == "i386-efi":
        efi_arch = "ia32"
    elif args.platform == "x86_64-efi":
        efi_arch = "x64"
    else:
        efi_arch = ""

    with tempfile.NamedTemporaryFile(mode="w+t") as grub_early:
        if args.pxe:
# net_get_dhcp_option net_default_server pxe:dhcp 66 string
            grub_early.write("""
set pldnr_prefix=/pld-nr
set netboot=yes
set prefix=($root)$pldnr_prefix/boot/grub
load_env -f ($root)/pld-nr-net.env
echo "using pldnr_prefix: $pldnr_prefix prefix: $prefix"
""")
        else:
            grub_early.write("""
echo "starting grub ({platform})"
search.fs_uuid {vol_id} root
search.fs_uuid {efi_id} efi_part
set pldnr_prefix=
set prefix=($root)/boot/grub
set efi_suffix={efi_suffix}
echo "using prefix: $prefix efi_part: $efi_part $efi_suffix"
"""
                     .format(platform=args.platform,
                             vol_id=config.cd_vol_id,
                             efi_id=config.efi_vol_id,
                             efi_suffix=efi_arch.upper()))
        grub_early.flush()
        platform = args.platform
        grub_core_modules = ["minicmd", "echo"]
        if args.pxe:
            if args.platform.endswith("-pc"):
                platform += "-pxe"
                grub_core_modules += ["pxe"]
            else:
                grub_core_modules += ["efinet"]
            grub_core_modules += ["tftp", "loadenv"]
            prefix = "/pld-nr/boot/grub"
        else:
            if args.platform.endswith("-pc"):
                grub_core_modules += ["biosdisk"]
            grub_core_modules += ["iso9660", "search", "search_label",
                                    "fat", "part_gpt", "iso9660"]
            prefix = "/boot/grub"
        logger.debug("Making {} grub image for {} with modules: {!r}"
                        .format(args.destination, args.platform,
                                                    grub_core_modules))
        subprocess.check_call(["grub-mkimage",
                                "--output", args.destination,
                                "--format", platform,
                                "--prefix", prefix,
                                "--config", grub_early.name,
                                ] + grub_core_modules)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
