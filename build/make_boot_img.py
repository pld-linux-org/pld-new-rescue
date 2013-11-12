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

HEADS = 255
SECTORS = 32
SECTOR = 512
CYLINDER = HEADS*SECTORS*SECTOR

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
                         .format(config.hd_vol_id))
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
    parser = argparse.ArgumentParser(description="Make boot image",
                                     parents=[log_parser])
    parser.add_argument("destination",
                        help="Destination file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    boot_img_fn = os.path.abspath(args.destination)
    root_dir = os.path.abspath("root")
    boot_img_dir = os.path.abspath("../boot_img")
    init_cpio_fn = os.path.abspath("init.cpi")
    vmlinuz_fn = os.path.abspath("root/boot/vmlinuz")
    boot_mnt_dir = os.path.abspath("boot_mnt")
    if not os.path.isdir(boot_mnt_dir):
        os.makedirs(boot_mnt_dir)
    pldnr_dir = os.path.join(boot_mnt_dir, "pld-nr-{0}".format(config.bits))
    grub_early_fn = os.path.abspath("grub_early.cfg")
    grub_prefix = "grub"

    module_files = []
    for module in config.modules:
        module_files.append(os.path.abspath("{0}.cpi".format(module)))

    logger.info("Computing required image size")
    du_output = subprocess.check_output(["du", "-sbcD",
                                            "/lib/grub",
                                            boot_img_dir,
                                            init_cpio_fn,
                                            vmlinuz_fn,
                                            ] + module_files)
    match = DU_OUTPUT_RE.search(du_output.decode("utf-8"))
    bytes_needed = int(int(match.group(1)) * 1.1)
    logger.debug("bytes needed: {0!r}".format(bytes_needed))
    cylinders_needed = max(bytes_needed // CYLINDER + 2, 2)
    logger.debug("cylinders needed: {0!r}".format(cylinders_needed))

    logger.info("Creating the image")
    subprocess.check_call(["dd", "if=/dev/zero", "of=" + boot_img_fn,
                            "bs={0}".format(CYLINDER),
                            "count={0}".format(cylinders_needed)])
    try:
        lodev = subprocess.check_output(["losetup", "--partscan", "--find",
                                                        "--show", boot_img_fn])
        lodev = lodev.decode("utf-8").strip()
        try:
            sfdisk_p = subprocess.Popen(["sfdisk",
                                         "-H", str(HEADS),
                                         "-S", str(SECTORS),
                                         "-C", str(cylinders_needed),
                                         lodev],
                                        stdin=subprocess.PIPE)
            sfdisk_p.communicate(b"1,+,e,*\n0,0,0\n0,0,0\n0,0,0\n")
            rc = sfdisk_p.wait()
            if rc:
                raise subprocess.CalledProcessError(rc, ["sfdisk"])
            subprocess.check_call(["mkdosfs", "-F", "16", "-I",
                                    "-i", config.hd_vol_id.replace("-", ""),
                                    lodev + "p1"])
            subprocess.check_call(["mount", "-t", "vfat",
                                    "-o", "utf8=true",
                                    lodev + "p1", boot_mnt_dir])
            try:
                logger.info("Installing PLD NR files")
                os.makedirs(pldnr_dir)
                shutil.copy(vmlinuz_fn,
                            os.path.join(pldnr_dir, "vmlinuz"))
                shutil.copy(init_cpio_fn,
                            os.path.join(pldnr_dir, "init.cpi"))
                for module_f in module_files:
                    module_fn = os.path.basename(module_f)
                    shutil.copy(module_f,
                            os.path.join(pldnr_dir, module_fn))
                if config.memtest86:
                    shutil.copy("/boot/memtest86", boot_mnt_dir)
                if config.memtest86_plus:
                    shutil.copy("/boot/memtest86+", boot_mnt_dir)
                config.copy_template_dir(boot_img_dir, boot_mnt_dir)
                for platform in config.grub_platforms:
                    install_grub(config, platform, lodev, boot_mnt_dir,
                                                grub_prefix, grub_early_fn)
            finally:
                subprocess.call(["umount", boot_mnt_dir])
        finally:
            subprocess.call(["losetup", "-d", lodev])
    except:
        os.unlink(boot_img_fn)
        raise

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
