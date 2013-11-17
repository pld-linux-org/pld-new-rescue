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

logger = logging.getLogger()

DU_OUTPUT_RE = re.compile("^(\d+)\s+total", re.MULTILINE)

def install_grub(config, platform, lodev, boot_mnt_dir, grub_prefix,
                                                            grub_early_fn):
    logger.info("Installing GRUB for {0}".format(platform))
    grub_prefix_dir = os.path.join(boot_mnt_dir, grub_prefix)
    grub_plat_dir = os.path.join(grub_prefix_dir, platform)
    if not os.path.exists(grub_plat_dir):
        os.makedirs(grub_plat_dir)
    if platform.endswith("-efi"):
        efi_dir = os.path.join(boot_mnt_dir, "EFI/BOOT")
        if not os.path.exists(efi_dir):
            os.makedirs(efi_dir)
        if "64" in platform:
            efi_arch = "X64"
        else:
            efi_arch = "IA32"
        grub_img_fn = os.path.join(efi_dir, "BOOT{}.EFI".format(efi_arch))
    else:
        grub_img_fn = os.path.join(grub_plat_dir, "core.img")
        efi_arch = ""

    with open(grub_early_fn, "wt") as grub_early:
        grub_early.write("echo \"starting grub\"\n"
                         "search.fs_uuid {} root\n"
                         "set prefix=($root)/grub\n"
                         .format(config.efi_vol_id))
        if platform.endswith("-efi"):
            # grub does not recognize partitions of the EFI eltorito image
            # so let's try the other way round
            grub_early.write("configfile $prefix/go_normal.cfg\n"
                            "echo \"boot partition not found"
                                    " falling back to loopback device\"\n"
                            "search.fs_uuid {} cd\n"
                            "loopback loop ($cd)/pld-nr-{}.img\n"
                            "set root=(loop,msdos1)\n"
                            "set prefix=($root)/grub\n"
                            .format(efi_arch, config.cd_vol_id, config.bits))

    grub_core_modules = ["search", "search_label", "fat", "part_msdos", "echo"]
    if platform.endswith("-pc"):
        grub_core_modules += ["biosdisk", "minicmd"]
    elif platform.endswith("-efi"):
        grub_core_modules += ["iso9660", "loopback", "configfile"]
    subprocess.check_call(["grub-mkimage",
                            "--output", grub_img_fn,
                            "--format", platform,
                            "--prefix", "/grub",
                            "--config", grub_early_fn,
                            ] + grub_core_modules)
    if platform.endswith("-pc"):
        shutil.copy("/lib/grub/{0}/boot.img".format(platform),
                                os.path.join(grub_plat_dir, "boot.img"))
        subprocess.check_call(["grub-bios-setup",
                                "--directory", grub_plat_dir,
                                lodev])
    elif platform.endswith("-efi"):
        subprocess.check_call(["grub-mkfont",
                                "--output", os.path.join(grub_prefix_dir,"font.pf2"),
                                "/usr/share/fonts/TTF/DejaVuSansMono.ttf"])
    config.copy_dir("/lib/grub/{0}".format(platform), grub_plat_dir)

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
