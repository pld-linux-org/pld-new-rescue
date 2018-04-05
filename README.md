
PLD New Rescue
==============

https://github.com/Jajcus/pld-new-rescue

Bootable disk image with 'live' [PLD Linux](http://www.pld-linux.org/) system
aimed especially for system rescue and maintenance.

This project is inspired by the original [PLD Rescue CD](http://rescuecd.pld-linux.org/)

This is still work in progress.

List of packages included in image should be available with the binary releases.

### About this version

This is the 'th-2016' branch of the PLD New Rescue, based on most current
PLD Linux Th packages. Due to the dynamic nature of PLD Th and its package
repositories, what builds and works today may fail to build or work tomorrow.
But the software is more up to date.

For newest packages use code from the 'th-current' branch.

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

The `/boot/pld-nr-net.env` may be edited (preferably with the `grub-editenv`
utility) to customize PLD NR boot. It may be especially useful to set the `pldnr_option`
variable there, to add custom options (like `pldnr.keys=` to the kernel command line).

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
        match if substring (option vendor-class-identifier, 0, 9) = "PXEClient"
             or substring (option vendor-class-identifier, 0, 14) = "pld-new-rescue";
        if option arch = 00:06 {
          filename "/pld-nr/boot/net_ia32.efi";
        } else if option arch = 00:07 {
          filename "/pld-nr/boot/net_x64.efi";
        } else {
          filename "/pld-nr/boot/netboot.pxe";
        }
        option tftp-server-name "192.168.10.1";
        next-server 192.168.10.1;
      }
    }

If the DHCP server has support for 'ignore-client-uids on;' configuration flag
it may be a good idea to add it to the config file to prevent the system from
switching IP addresses during boot.

### iSCSI boot

Normally only the 'All in RAM' boot options are available when booting via PXE,
as the boot medium is not available on the remote machine, but it may be made
available via iSCSI.

To enable the 'Minimum RAM' boot options and boot PLD NR from iSCSI one needs
to set the iSCSI target parameters in the `pld-nr-net.env` file on the TFTP
root directory.

The `pldnr_iscsi` variable should be set to:
`[<host>[:<port>]/]<target_name>[=<initiator_name>]`

Only the `<target_name>` is mandatory, the other parameters defaults are:

* `<host>` – the boot server address (provided with the `tftp-server-name`
  DHCP option or through the `ip=` kernel parameter)

* `<port>` – 3260

* `<initiator_name>` – automatically generated initiator name:
  "`iqn.2014-01.net.jajcus.pld-nr:boot:`" followed with the MAC address
  of the boot interface (lower-case digits, no delimiters)

Kernel command-line options
---------------------------

* `init=<path>` – init binary (default: `/sbin/init`)

* `pldnr.debug` – enable initramfs debugging

* `pldnr.nomedia` – do not mount the boot media in initramfs ('minimum RAM' boot
  mode won't work)

* `pldnr.modules=<module>,<module>...` – PLD NR modules to load (order matters)

* `pldnr.keymap=<name>` – keymap (default: from build.conf)

* `pldnr.font=<name>` – font (default: from build.conf)

* `pldnr.sshpw=yes` – enable SSH password authentication

* `ip=<client-ip>:<server-ip>:<gw-ip>:<netmask>:<hostname>:<device>:<autoconf>:<dns0-ip>:<dns1-ip>`
  ip=off/none/on/any/dhcp – how to configure early network (by default use DHCP, but only when needed)

* `pldnr.netdev=<device>` – network device name or MAC-address for early network

* `pldnr.keys=<url>` – URL (tftp:, http: or ftp:) where to load SSH
  `authorized_keys` for the root user. Host name may be omitted in the URL – the server
  address obtained through DHCP (`tftpp-server-name` option or `next-server`) or from the `ip=`
  kernel option will be used then.

* `pldnr.iscsi=[<host>[:<port>]/]<target_name>[=<initiator_name>]` – iSCSI
  connection settings. This should be set through the '`pldnr_iscsi`' variable
  in the `pld-nr-net.env` file.

* `pldnr.newifnames` – enable udev's predictable network interface names

Limited customization
---------------------

It's possible to add/overwrite files and provide custom shell scripts to be executed before the
initramfs boot scripts give up control to systemd. This way you can apply changes to a rescuecd
environment without having to rebuild the whole image.

The initramfs boot script checks for the existence of a /custom directory and copies its
contents to the final system's / directory (which is mounted as /root while initramfs is in
control). Afterwards any /custom*.sh shell scripts are executed.

Both the /custom directory and /custom*.sh shell script(s) can by provided by creating at least
one custom cpio archive and modifying the proper boot configs. An example is better than a long
description, so below is how a custom cpio archive (called 'custom.cpi') looks like in a 64 bit
PXE boot environment. This sample module overrides /etc/issue and runs a single custom.sh
script (which could've also been named custom1.sh if there were more than one).

[root@dev2 pld-nr-64]# ls
_init.cpi  _net.cpi  base.cpi  basic.cpi  custom.cpi  rescue.cpi  vmlinuz
[root@dev2 pld-nr-64]# cpio -i -t <custom.cpi 
custom.sh
custom
custom/etc
custom/etc/issue

A few things to keep in mind regarding this mechanism:
1. If you want to add some software, it's probably a better idea to make a whole custom build
   of the rescuecd. It's not that hard and will probably be much more easily maintainable.
2. If you want to provide ssh authorized_keys, the pldnr.keys kernel command-line option is
   likely a better idea.
3. Overriding whole config files to modify a single parameter is likely overkill and might
   lead to issues in the future. It's probably better to write a short sed script that modifies
   just that one parameter and put that in a /custom*.sh script.
4. If you need full control of the file copy procedure, instead of providing a /custom
   directory (and letting rescuecd do the copying for you), you can add for example a /customX
   directory and take care of copying its contents to /root from inside your /custom*.sh script.

### PXE boot

You need to add the new module (cpio file) both to pld-nr-net.env (use `grub-editenv`) and
grub.conf (search for 'base basic rescue', that's where the modules are defined). If you don't
do both, your module will not be detected properly.

Rebuilding and full customization
---------------------------------

Check-out code from https://github.com/Jajcus/pld-new-rescue (versions on different
branches and tags may provide different features or base on different PLD Linux versions).

Edit the `build.conf` file according to your needs. Please note that only the default
settings were properly tested. So, keeping the defaults is a good idea.

Put extra RPM packages needed to build this release (which are not available in
the source PLD repository) in the `extra_packages/th-2016/$arch` directory. The
packages needed should be available in a tar archive released with the latest
PLD NR binary release.

These provide features that are required by this image, but not available in
the source repository used as a base for this build (to provide reproducible
results).

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
    - `deps_workaround.pset`: similar to `packages.pset` but installed before
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

    - `initramfs/init.files` lists special files and directories to be made in
      the basic initramfs and files which should be moved there from the base
      module.
    - `initramfs/init.skel` directory contains additional files to be included in
      the basic initramfs, including the main `init` script.
    - `initramfs/net.files` lists special files and directories to be made in
      the early network initramfs add-on (_net.cpi) and files which should be
      moved there from the base module.
    - `initramfs/net.skel` directory contains additional files to be included in
      the  early network initramfs add-on (_net.cpi).

  * Add or replace RPM files in the `extra_packages/` subdirectories. These
    are used only when pulled through a module 'pset' files (directly or
    through dependencies).

Directories `iso_templ/`, `efi_templ/` and `initramfs/skel` may contain files
with `.pldnrt` extension (PLD NR template). `@variable@` strings in those
files will be replaced with variable values and the result will be saved 
to a file with the extensions stripped. Available variables can be checked
with the `build/pld_nr_buildconf.py` command.
