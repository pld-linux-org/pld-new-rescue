#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import logging
import struct
from glob import glob

from hashlib import md5

import pld_nr_buildconf

logger = logging.getLogger("make_iso_img")

# Report layout: xt , Startlba ,   Blocks , Filesize , ISO image path
HDBOOT_LBA_RE = re.compile(br"File data lba:"
                            br"\s*(?P<xt>\d+)\s*,"
                            br"\s*(?P<start_lba>\d+)\s*,"
                            br"\s*(?P<blocks>\d+)\s*,"
                            br"\s*(?P<filesize>\d+)\s*,"
                            br"\s*'/boot/boot.img'\s*")

# grub/i286/pc/boot.h
GRUB_BOOT_MACHINE_DRIVE_CHECK = 0x66
GRUB_BOOT_MACHINE_BPB_START = 0x3
GRUB_BOOT_MACHINE_BPB_END = 0x5a
GRUB_BOOT_MACHINE_KERNEL_SECTOR = 0x5c
GRUB_BOOT_MACHINE_BOOT_DRIVE = 0x64
GRUB_BOOT_MACHINE_PART_START = 0x1be
GRUB_BOOT_MACHINE_PART_END = 0x1fe
GRUB_BOOT_MACHINE_LIST_SIZE = 12

GRUB_BLOCK_LIST = 0x200 - GRUB_BOOT_MACHINE_LIST_SIZE

def patch_image_mbr(config, image):
    lba_report = subprocess.check_output(["xorriso",
                                        "-dev", image,
                                        "-find", "/boot/boot.img",
                                            "-exec", "report_lba"])
    match = HDBOOT_LBA_RE.search(lba_report)
    if not match:
        logger.error("Could not find /boot/boot.img LBA")
        sys.exit(1)
    start_lba = int(match.group("start_lba"))
    blocks = int(match.group("blocks"))
    filesize = int(match.group("filesize"))
    logger.info("/boot/boot.img start CD LBA: {} blocks: {} bytes: {}"
                                        .format(start_lba, blocks, filesize))
    start_sector = start_lba * 4
    if filesize & 0x1ff:
        sectors = (filesize >> 9) + 1
    else:
        sectors = filesize >> 9
    logger.info("/boot/boot.img start HD LBA: {} sectors: {}"
                                        .format(start_sector, sectors))

    with open(image, "r+b") as image_f:
        image_f.seek(0)
        buf = bytearray(512)
        image_f.readinto(buf)

        if b"GRUB" not in buf:
            logger.error("GRUB not found in MBR")
            sys.exit(1)
        if not buf.endswith(b"\x55\xaa"):
            logger.error("The first 512 bytes of the image do not look like"
                                                                    " an MBR")
            sys.exit(1)

        cur_boot_drive = buf[GRUB_BOOT_MACHINE_BOOT_DRIVE]
        logger.debug("Current BIOS boot drive: {:0x}".format(cur_boot_drive))
        cur_kernel_sector = struct.unpack("q", 
                                buf[GRUB_BOOT_MACHINE_KERNEL_SECTOR
                                    :GRUB_BOOT_MACHINE_KERNEL_SECTOR+8])[0]
        logger.debug("Current kernel sector: {:0x}".format(cur_kernel_sector))

        logger.debug("Looking for GRUB core image start...")
        for i in (1, 4, 8):
            image_f.seek((start_sector + i) * 512)
            data = image_f.read(2)
            if data == b"RV":
                logger.debug("  found at offset {} sectors".format(i))
                core_offset = i
                break
        else:
            logger.debug("  not found. Assumming 1 sector offser")
            core_offset = 1

        logger.info("Patching GRUBs MBR")

        # set the address of the kernel
        buf[GRUB_BOOT_MACHINE_KERNEL_SECTOR:GRUB_BOOT_MACHINE_KERNEL_SECTOR+8
                ] = struct.pack("q", start_sector + core_offset)
        image_f.seek(0)
        image_f.write(buf)

        # enable drive check logic
        buf[GRUB_BOOT_MACHINE_DRIVE_CHECK:GRUB_BOOT_MACHINE_DRIVE_CHECK + 2
                ] = b"\x90\x90"
        
        image_f.seek((start_sector + core_offset) * 512)
        image_f.readinto(buf)

        buf[GRUB_BLOCK_LIST:GRUB_BLOCK_LIST+10] = struct.pack("qh",
                                                start_sector + core_offset + 1,
                                                sectors - core_offset - 1)
        image_f.seek((start_sector + core_offset) * 512)
        image_f.write(buf)

def write_netenv_file(netenv_fn, net_files):
    subprocess.check_call(["grub-editenv", netenv_fn, "create"])
    subprocess.check_call(["grub-editenv", netenv_fn,
                                        "set", "pldnr_prefix=/pld-nr"])
    subprocess.check_call(["grub-editenv", netenv_fn,
                                    "set", "pldnr_net_files=:{}:"
                                                .format(":".join(net_files))])

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(
                                description="Make hybrid ISO/GPT boot image",
                                parents=[log_parser])
    parser.add_argument("destination",
                        help="Destination image file name")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)

    config = pld_nr_buildconf.Config.get_config()

    root_dir = os.path.abspath("root")
    tmp_img_dir = os.path.abspath("tmp_img")
    templ_dir = os.path.abspath("../iso_templ")
    netenv_fn = os.path.abspath("pld-nr-net.env")
    net_files = []
    vmlinuz_fn = os.path.join(root_dir, "boot/vmlinuz")
    while os.path.islink(vmlinuz_fn):
        link_target = os.readlink(vmlinuz_fn)
        link_target = os.path.join("/boot", link_target)
        vmlinuz_fn = os.path.join(root_dir, link_target.lstrip("/"))

    if os.path.exists(args.destination):
        os.unlink(args.destination)

    if os.path.exists(tmp_img_dir):
        shutil.rmtree(tmp_img_dir)

    os.makedirs(tmp_img_dir)
    try:
        logger.debug("Copying ISO contents template")
        config.copy_template_dir(templ_dir, tmp_img_dir)

        logger.debug("Creating the ISO image")
        command = ["xorriso",
                "-report_about", "ALL",
                "-dev", args.destination,
                "-in_charset", "utf-8",
                "-out_charset", "utf-8",
                "-hardlinks", "on",
                "-acl", "off",
                "-xattr", "off",
                "-pathspecs", "on",
                "-uid", "0",
                "-gid", "0",

                "-joliet", "on",
                "-rockridge", "on",
                "-volid", "PLD_NR",
                "-volume_date", "uuid", config.cd_vol_id.replace("-", ""),
                ]
        if config.bios and "i386-pc" in config.grub_platforms:
            # CD boot
            command += ["-add", "/boot/boot.img=boot.img", "--"]
            command += ["-boot_image", "grub", "bin_path=/boot/boot.img"]
            command += ["-boot_image", "grub", "next"]
            
            # HDD boot
            command += ["-boot_image", "any",
                                    "system_area=/lib/grub/i386-pc/boot.img"]
            command += ["-boot_image", "any", "next"]
            # MBR and the image will be patched later

        if config.efi:
            command += ["-add", "/boot/efi.img=efi.img", "--"]
            command += ["-boot_image", "any", "efi_path=/boot/efi.img"]
            command += ["-boot_image", "any", "next"]
            command += ["-boot_image", "any", "efi_boot_part=--efi-boot-image"]
            command += ["-boot_image", "any", "next"]

        command.append("-add")
        for plat in config.grub_platforms:
            src_dir = os.path.join("/lib/grub", plat)
            for path in glob(os.path.join(src_dir, "*")):
                if path.endswith(".module"):
                    continue
                dst_path = "/boot/grub" + path[len("/lib/grub"):]
                command.append("{}={}".format(dst_path, path))
        pld_nr_prefix = "pld-nr-{}".format(config.bits)
        command.append("/{}/init.cpi=init.cpi".format(pld_nr_prefix))
        net_files.append("{}/init.cpi".format(pld_nr_prefix))
        for mod in config.modules:
            command.append("/{0}/{1}.cpi={1}.cpi".format(pld_nr_prefix, mod))
            net_files.append("{}/{}.cpi".format(pld_nr_prefix, mod))
        command.append("/{}/vmlinuz={}".format(pld_nr_prefix, vmlinuz_fn))
        net_files.append("{}/vmlinuz".format(pld_nr_prefix))
        if config.efi:
            command.append("/boot/grub/font.pf2=font.pf2")
        command.append("/={}".format(tmp_img_dir))
        if config.memtest86:
            command.append("/boot/memtest86=/boot/memtest86")
            net_files.append("boot/memtest86")
        if config.memtest86_plus:
            command.append("/boot/memtest86_p=/boot/memtest86+")
            net_files.append("boot/memtest86_p")
        for img in config.net_grub_images:
            command.append("/boot/{0}={0}".format(img))
        if config.net_grub_images:
            write_netenv_file(netenv_fn, net_files)
            command.append("/boot/pld-nr-net.env={}".format(netenv_fn))
        command.append("--")

        subprocess.check_call(command)
        
        if config.bios and "i386-pc" in config.grub_platforms:
            patch_image_mbr(config, args.destination)
    finally:
        shutil.rmtree(tmp_img_dir)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et
