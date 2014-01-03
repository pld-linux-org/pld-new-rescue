
PLD New Rescue
==============

https://github.com/Jajcus/pld-new-rescue

Bootable disk image with 'live' [PLD Linux](http://www.pld-linux.org/) system
aimed especially for system rescue and maintenance.

This project is inspired by the original [PLD Rescue CD](http://rescuecd.pld-linux.org/)

This is still work in progress.

List of packages included in image should be available with the binary releases.

### About this version

This is the 'master' branch of the PLD New Rescue, based on a frozen
'Th 2013' snapshot of PLD Linux. It may be old but is guaranteed not to change,
so if the code builds now it should build next month or year too (provided the
build environment doesn't change to much and the same 'extra packages' are
provided).

For current software, try your luck with code from the 'th-current' branch.

Goals
-----

* The image should be compatible with modern computers. This means 64-bit and
  EFI support. (got it!)

* The image should be compatible with old computers. This means 32-bit support
  and low memory requirements. (got it!)

* It should be as easy to boot it from a USB disk as from a CD (got it!)

* Setting up a network boot (PXE, including EFI PXE) should be easy too.

* Everyone familiar with PLD Linux should be able to build and customize 
  the image. (got it?)

* Support for EFI secure boot would be great too (not implemented yet)

Usage
-----

Write the generated hybrid ISO image to a cdrom:

    cdrecord dev=/dev/sr0 pld-nr-64.iso

or to an usb stick:

    cat pld-nr-64.iso > /dev/sdX

(where /dev/sdX is the USB stick device name).

Then boot a system from the CD or USB stick. That should work.

When system boots one can log-in as 'root' using the 'pld' password.
SSH login is available only through key authentication and no public
keys are provided in the image by default.

Network boot
------------

The image now also supports PXE boot (but only in the 'All in RAM' mode).

To set up the network boot the following are needed:

* the PLD NR image or its contents

* a DHCP server

* a TFTP server

### TFTP server configuration

The TFTP server must be able to handle big files through block number roll-over.
*tftpd-hpa* does work correctly.

Copy the `/boot/pld-nr-net.env` file from the PLD NR image to the your TFTP
root directory and mount PLD NR image at, or copy its contents to, the
`/pld-nr` directory under the TFTP root.

Start the TFTP server to listen on the right network interface.

### DHCP server configuration

The DHCP server must provide IP address, TFTP server address and boot image
file name to the machine to be booted.

Here is a sample config file for ISC DHCP daemon for booting PLDNR:

    allow booting;
    allow bootp;
    
    default-lease-time 600;
    max-lease-time 7200;
    
    ddns-update-style none;
    
    option arch code 93 = unsigned integer 16; # RFC4578
    
    subnet 192.168.10.0 netmask 255.255.255.0 {
      range dynamic-bootp 192.168.10.100 192.168.10.200;
      option routers 192.168.10.1;
    
      class "pxeclients" {
        match if substring (option vendor-class-identifier, 0, 9) = "PXEClient";
        next-server 192.168.10.1;
        option tftp-server-name "192.168.10.1";
        if option arch = 00:06 {
          filename "/pld-nr/boot/net_ia32.efi";
        } else if option arch = 00:07 {
          filename "/pld-nr/boot/net_x64.efi";
        } else {
          filename "/pld-nr/boot/netboot.pxe";
        }
      }
    }

Kernel command-line options
---------------------------

* init=<path> – init binary (default: /sbin/init)

* pldnr.debug – enable initramfs debugging

* pldnr.nomedia – do not mount the boot media in initramfs ('minimum RAM' boot
  mode won't work)

* pldnr.modules=<module>,<module>... – PLD NR modules to load (order matters)

* pldnr.keymap=<name> – keymap (default: from build.conf)

* pldnr.font=<name>... – font (default: from build.conf)

* pldnr.sshpw=yes – enable SSH password authentication

* ip=<client-ip>:<server-ip>:<gw-ip>:<netmask>:<hostname>:<device>:<autoconf>:<dns0-ip>:<dns1-ip>
  ip=off/none/on/any/dhcp – how to configure early network (by default use DHCP, but only when needed)

* pldnr.netdev=<device> – network device name or MAC-address for early network

Building and customizations
---------------------------

Check-out code from https://github.com/Jajcus/pld-new-rescue (versions on different
branches and tags may provide different features or base on different PLD Linux versions).

Edit the `build.conf` file according to your needs. Please note that only the default
settings were properly tested. So, keeping the defaults is a good idea.

Put extra RPM packages needed to build this release (which are not available in
the source PLD repository) in the `extra_packages/$arch` directory. The
packages needed should be available in a tar archive released with the latest
PLD NR binary release.

Currently the extra packages needed are:

    SysVinit-tools-2.88-15
    coreutils-8.20-2
    db5.2-5.2.42.0-2
    db5.2-sql-5.2.42.0-2
    fsck-2.24-1
    glibc-2.18-3
    glibc-libcrypt-2.18-3
    glibc-misc-2.18-3
    iconv-2.18-3
    ldconfig-2.18-3
    libblkid-2.24-1
    libgomp-4.8.2-1
    libmount-2.24-1
    libsemanage-2.1.6-2
    libuuid-2.24-1
    localedb-src-2.18-3
    mount-2.24-1
    poldek-0.30.0-3
    poldek-libs-0.30.0-3
    rpm-5.4.13-6
    rpm-base-5.4.13-6
    rpm-lib-5.4.13-6
    rpm-utils-5.4.13-6
    ustr-1.0.4-2
    util-linux-2.24-1

These provide features that are required by this image, but not available in
the PLD Linux 'Th 2013' snapshot, which is used as a base for this build (to
provide reproducible results).

When the preparations are done calling 'make' in the main directory of the
distribution should start the build.

Please note that 'root' privileges are required for the process. Only the
'root' user or other user with full privileges granted via 'sudo' can build PLD
NR (enabling 'only the commands actually used by PLD NR build' still gives the
user full root access). Things are much easier this way. But it also can make
some mistakes catastrophic. So be careful!

For further customization one can also:

  * Edit or add files in the `iso_templ/` directory. Those will be copied to
    the final ISO image.
  * Edit or add files in the `efi_templ/` directory. Those will be copied to
    the EFI system partition and are generally relevant only for the EFI boot.
  * Edit the *poldek* configuration in `modules/poldek.conf` (note that
    may affect what packages and package versions are installed and other
    parts of the framework may not be compatible with the changes)
  * Edit or add modules in the `modules/` directory.

    Each directory represent a single 'module' part of the PLD NR system. They
    are built incrementaly, so every module depends on the modules before it.
    Module order is defined in the `build.conf` file. And the `base` module is
    special, as it is used for the initramfs build too.

    Each module is defined by the following files:

    - `packages.pset`: list of packages to install in addition to the packages
      installed by previous modules.
    - `conds_workaround.pset`: similar to `packages.pset` but installed before
      `packages.pset` and with `--nodeps --nofollow` options. Used to
      work-around broken dependencies in PLD package repositories.
    - `post-install.sh`: script which will be run after the packages are
      installed. Its working directory will be the `build/` directory.
      Configuration variables (those in `build.conf` and some derived from
      them) will be available in `$pldnr_*` environment variables. The script
      should only modify files under `root/` and may use `chroot root ...`
      command to execute code in the system being built.
    - `pre-install.sh`: same as `post-install.sh` but run before the packages
      are installed
    - `init.sh`: this script will be included in the initramfs and run just
      after the module has been attached to the target root filesystem.

  * Edit files under `initramfs`:

    - `initramfs/files.list` lists special files and directories to be made in
      the initramfs and files which should be moved there from the base
      module
    - `initramfs/skel` directory contains additional files to be included in
      the initramfs, including the main `init` script.

  * Add or replace RPM files in the `extra_packages/` subdirectories. These
    are used only when pulled through a module 'pset' files (directly or
    through dependencies).

Directories `iso_templ/`, `efi_templ/` and `initramfs/skel` may contain files
with `.pldnrt` extension (PLD NR template). `@variable@` strings in those
files will be replaced with variable values and the result will be saved 
to a file with the extensions stripped. Available variables can be checked
with the `build/pld_nr_buildconf.py` command.
