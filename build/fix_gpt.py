#!/usr/bin/python3

"""Fix broken GPT created by xorriso."""

import argparse
import sys
import os
import stat
import struct
import ctypes
import logging
import fcntl
import uuid
import zlib
import copy

import pld_nr_buildconf

logger = logging.getLogger("fix_gpt")

# /usr/include/asm-generic/ioctl.h
def _IO(type_, nr):
    return (type_ << 8) + nr
def _IOR(type_, nr, size):
    return 0x80000000 | (size << 16) | (type_ << 8) + nr

# /usr/include/linux/fs.h
BLKSSZGET = _IO(0x12, 104)
BLKGETSIZE64 = _IOR(0x12, 114, ctypes.sizeof(ctypes.c_size_t))

class GPTError(Exception):
    pass

class Partition(object):
    def __init__(self, type_uuid, part_uuid, first_lba, last_lba, flags, name):
        self.type_uuid = type_uuid
        self.part_uuid = part_uuid
        self.first_lba = first_lba
        self.last_lba = last_lba
        self.flags = flags
        self.name = name
    def __repr__(self):
        return "Partition({!r},{!r},{!r},{!r},{:016x},{!r}".format(
                str(self.type_uuid), str(self.part_uuid),
                self.first_lba, self.last_lba,
                self.flags, self.name)
    def as_bytes(self):
        name = self.name[:36]
        name += "\x00" * (36 - len(name))
        name = name.encode("UTF-16LE")
        return struct.pack("<16s16sQQQ72s",
                           self.type_uuid.bytes,
                           self.part_uuid.bytes,
                           self.first_lba,
                           self.last_lba,
                           self.flags,
                           name)
    @classmethod
    def from_bytes(cls, data):
        (type_uuid, part_uuid, first_lba, last_lba, flags, name
            ) = struct.unpack("<16s16sQQQ72s", data)
        type_uuid = uuid.UUID(bytes=type_uuid)
        part_uuid = uuid.UUID(bytes=part_uuid)
        name = name.decode("UTF-16LE").split("\x00")[0]
        return cls(type_uuid, part_uuid, first_lba, last_lba, flags, name)

class GPT(object):
    def __init__(self, image_f, image_size, lba_size, header=None, address=1,
                    is_backup=False):
        self.image_f = image_f
        self.image_size = image_size
        self.lba_size = lba_size
        self.address = address
        self.is_backup = is_backup
        self.something_wrong = False
        if not header:
            image_f.seek(lba_size * address)
            header = bytearray(lba_size)
            if image_f.readinto(header) != lba_size:
                raise GPTError("Short read at LBA #{}".format(address))
            if header[:8] != b"EFI PART":
                raise GPTError("Data at LBA #{} does not look like GPT header"
                                                        .format(address))
            logger.debug("GPT header loaded")
        self.header = header
        self.revision = None
        self.header_size = None
        self.header_crc = None
        self.reserved1 = None
        self.current_lba = None
        self.backup_lba = None
        self.first_usable_lba = None
        self.last_usable_lba = None
        self.disk_uuid = None
        self.part_array_start = None
        self.part_array_size = None
        self.part_entry_size = None
        self.part_array_crc = None
        self.reserved2 = None
        self.partitions = []
        self.load_header()
        self.load_partitions()

    def __str__(self):
        result = """GPT:
    revision:         {0.revision[0]}.{0.revision[1]}
    header size:      {0.header_size}
    header CRC32:     0x{0.header_crc:08x}
    reserved1:        0x{0.reserved1:08x}
    current LBA:      {0.current_lba}
    backup LBA:       {0.backup_lba}
    first usable LBA: {0.first_usable_lba}
    last usable LBA:  {0.last_usable_lba}
    disk UUID:        {0.disk_uuid}
    part array start: {0.part_array_start}
    no partitions:    {0.part_array_size}
    part entry size:  {0.part_entry_size}
    part array CRC32: 0x{0.part_array_crc:08x}
    reserved2:        {0.reserved2!r}
""".format(self)
        if self.partitions:
            result += "    partitions:\n"
            for num, part in enumerate(self.partitions):
                if part:
                    result += "      {:3}: {}\n".format(num, repr(part))
        return result

    def load_header(self):
        (signature,
                rev2, rev1,
                self.header_size,
                self.header_crc,
                self.reserved1,
                self.current_lba,
                self.backup_lba,
                self.first_usable_lba,
                self.last_usable_lba,
                disk_uuid,
                self.part_array_start,
                self.part_array_size,
                self.part_entry_size,
                self.part_array_crc
                ) = struct.unpack("<8sHHLLLQQQQ16sQLLL", self.header[:92])
        self.revision = (rev1, rev2)
        if self.revision != (1, 0):
            logger.warning("Unknown GPT revision: {}"
                                                .format(".".join(revision)))
        if self.reserved1:
            logger.warning("Non zero value of the reserved field: {:08x}"
                                                .format(self.reserved1))
            if self.revision == (1, 0):
                self.something_wrong = True
        self.reserved2 = bytes(self.header[92:self.header_size])
        if self.reserved2.strip(b"\x00"):
            logger.warning("Non-zero data at the end of the header: {!r}"
                                                    .format(self.reserved2))
            if self.revision == (1, 0):
                self.something_wrong = True
        self.disk_uuid = uuid.UUID(bytes=disk_uuid)
        crc = self.compute_header_crc(self.header, self.header_size)
        if crc != self.header_crc:
            logger.warning("Bad GPT header CRC")
            self.something_wrong = True
        last_lba = (self.image_size // self.lba_size) - 1
        if self.current_lba != self.address:
            logger.warning("Current LBA is {}, should be {}"
                                .format(self.current_lba, self.address))
            self.something_wrong = True
        if self.is_backup:
            if self.backup_lba != 1:
                logger.warning("Backup LBA of the backup GPT wrong."
                                " Is: {} Should be: 1"
                                .format(self.backup_lba))
                self.something_wrong = True
        else:
            if self.current_lba != 1:
                logger.warning("Primary GPT current LBA is {}, should be 1"
                                            .format(self.current_lba))
                self.something_wrong = True
            if self.backup_lba != last_lba:
                logger.warning("Backup LBA not at the end of the device."
                                " Is: {} Should be: {}"
                                .format(self.backup_lba, last_lba))
                self.something_wrong = True
        if self.last_usable_lba >= (self.image_size // self.lba_size):
            logger.warning("Last usable LBA beyond the end of the device")
            self.something_wrong = True
        logger.debug("Loaded header:\n{}".format(self))
   
    @staticmethod
    def compute_header_crc(data, header_size):
        check_buf = bytearray(data[:header_size])
        check_buf[16:20] = b"\x00\x00\x00\x00"
        crc = zlib.crc32(check_buf) & 0xffffffff
        logger.debug("Computed CRC32 of the header: 0x{:08x}".format(crc))
        return crc
    
    def load_partitions(self):
        logger.debug("Loading partitions:")
        self.image_f.seek(self.lba_size * self.part_array_start)
        size = self.part_array_size * self.part_entry_size
        buf = bytearray(size)
        if self.image_f.readinto(buf) != size:
            raise GPTError("Short read of partition array")
        crc = zlib.crc32(buf) & 0xffffffff
        logger.debug("Computed CRC32 of the array: 0x{:08x}".format(crc))
        if crc != self.part_array_crc:
            logger.warning("Bad GPT partition array CRC")
            self.something_wrong = True
        self.partitions = [None] * self.part_array_size
        for num in range(self.part_array_size):
            data = buf[num*self.part_entry_size:(num+1)*self.part_entry_size]
            if not data.strip(b"\x00"):
                logger.debug("  {}: empty".format(num))
                continue
            partition = Partition.from_bytes(data)
            logger.debug("  {}: {!r}".format(num, partition))
            self.partitions[num] = partition

    def load_backup(self):
        return GPT(self.image_f,
                     image_size=self.image_size,
                     lba_size=self.lba_size,
                     address=self.backup_lba,
                     is_backup=True)

    def trim_partition_array(self, trim_to=128):
        if self.part_array_size == trim_to:
            return False
        logger.debug("Trimming partition array size to {} entries, if possible"
                                .format(trim_to))
        if self.part_array_size < trim_to:
            self.part_array_size = trim_to
        else:
            last_used = 0
            if self.partitions:
                for num, part in enumerate(self.partitions):
                    if part:
                        last_used = num
            if last_used >= self.part_array_size:
                return False
            self.part_array_size = max(trim_to, last_used - 1)
        if self.partitions:
            self.partitions = self.partitions[:self.part_array_size]
            if len(self.partitions) < self.part_array_size:
                self.partitions += [None] * (self.part_array_size
                                                        - en(self.partitions))
        else:
            self.partitions = [None] * self.part_array_size
        return True

    def make_backup(self):
        if self.is_backup:
            raise ValueError("make_backup supported only for primary GPT")
        logger.debug("Preparing backup GPT")
        backup_gpt = copy.copy(self)
        last_lba = (self.image_size // self.lba_size) - 1
        self.backup_lba = last_lba
        backup_gpt.current_lba = last_lba
        backup_gpt.backup_lba = self.address
        backup_gpt.header_crc = 0
        backup_gpt.part_array_crc = 0
        part_array_lbas = (self.part_array_size * self.part_entry_size
                                                        // self.lba_size)
        if self.part_array_size % self.lba_size:
            part_array_lbas += 1
        backup_gpt.part_array_start = backup_gpt.current_lba - part_array_lbas
        return backup_gpt

    def write(self):
        rev1, rev2 = self.revision
        partarray = bytearray(self.part_array_size * self.part_entry_size)
        for num, part in enumerate(self.partitions):
            if not part:
                continue
            part_ent_off = self.part_entry_size * num
            next_part_ent_off = part_ent_off + self.part_entry_size
            partarray[part_ent_off:next_part_ent_off] = part.as_bytes()

        self.part_array_crc = zlib.crc32(partarray) & 0xffffffff
        logger.debug("New partition array CRC: {}".format(self.part_array_crc))
        
        header = struct.pack("<8sHHLLLQQQQ16sQLLL",
                             b"EFI PART",
                             rev2, rev1,
                             self.header_size,
                             0,
                             self.reserved1,
                             self.current_lba,
                             self.backup_lba,
                             self.first_usable_lba,
                             self.last_usable_lba,
                             self.disk_uuid.bytes,
                             self.part_array_start,
                             self.part_array_size,
                             self.part_entry_size,
                             self.part_array_crc)
        header += self.reserved2
        if len(header) < self.lba_size:
            header += (self.lba_size - len(header)) * b"\x00"
        else:
            header[:self.lba_size]
        crc = zlib.crc32(header[:self.header_size]) & 0xffffffff
        logger.debug("New header CRC: {}".format(crc))
        
        self.header = bytearray(header)
        self.header[16:20] = struct.pack("<L", crc)
        self.header_crc = crc

        logger.debug("Writting GPT header at LBA#{}".format(self.current_lba))
        self.image_f.seek(self.lba_size * self.current_lba)
        self.image_f.write(self.header)

        logger.debug("Writting partition array at LBA#{}"
                                            .format(self.part_array_start))
        self.image_f.seek(self.lba_size * self.part_array_start)
        self.image_f.write(partarray)
        self.address = self.current_lba

def main():
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(
                                description="Fix broken GPT",
                                parents=[log_parser])
    parser.add_argument("image",
                        help="Image file or block device to fix")
    parser.add_argument("--write", action="store_true",
                        help="Write changes without asking")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not change anything")
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)

    if args.dry_run:
        mode = "rb"
    else:
        mode = "r+b"
    
    with open(args.image, mode) as image_f:
        image_st = os.fstat(image_f.fileno())
        if stat.S_ISBLK(image_st.st_mode):
            logger.debug("{} is a block device, reading its properties"
                                                        .format(args.image))
            uint64_buf = ctypes.c_uint64()
            if fcntl.ioctl(image_f.fileno(), BLKGETSIZE64, uint64_buf) < 0:
                raise IOError("ioctl BLKGETSIZE64 failed")
            image_size = uint64_buf.value
            logger.debug("  device size: {}".format(image_size))
            int_buf = ctypes.c_size_t()
            if fcntl.ioctl(image_f.fileno(), BLKSSZGET, int_buf) < 0:
                raise IOError("ioctl BLKSSZGET failed")
            logger.debug("  block size: {}".format(int_buf.value))
            if int_buf.value != 512:
                logger.warning("{} block size is {}, but this utility"
                        " currently works on 512-bytes blocks only."
                                        .format(args.image, int_buf.value))
        elif stat.S_ISREG(image_st.st_mode):
            image_size = os.fstat(image_f.fileno()).st_size
            logger.debug("image size: {}".format(image_size))
        else:
            logger.error("{} not a block device nor a regular file"
                                                        .format(args.image))
            sys.exit(1)
        if image_size & 0x1ff:
            logger.error("Image size not a multiply of 512!")
            sys.exit(1)
        try:
            primary_gpt = GPT(image_f,
                              image_size=image_size,
                              lba_size=512)
        except GPTError as err:
            logger.error("Could not read GPT at the second 512-bytes sector:"
                            " {}. Other sector sizes not supported yet."
                            .format(err))
            sys.exit(1)

        try:
            backup_gpt = primary_gpt.load_backup()
        except GPTError as err:
            logger.warning(err)

        if (primary_gpt.something_wrong or not backup_gpt
                                            or backup_gpt.something_wrong):
            logger.info("Problems found, will fix that.")
        elif primary_gpt.part_array_size != 128:
            logger.info("Strange partition array size ({}), will fix that.")
        else:
            logger.info("Everything seems OK. Nothing to do.")
            return

        primary_gpt.trim_partition_array()
        backup_gpt = primary_gpt.make_backup()
        
        logger.debug("New primary GPT:\n{}".format(primary_gpt))
        logger.debug("New backup GPT:\n{}".format(backup_gpt))

        if args.dry_run:
            logger.info("Skipping write.")
            return

        if not args.write:
            ans = input("Modify the image [y/N]?")
            if ans.lower() not in ("y", "yes"):
                return
        
        primary_gpt.write()
        backup_gpt.write()

if __name__ == "__main__":
    main()
