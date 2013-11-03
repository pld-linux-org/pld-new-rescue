
include make.inc

.PHONY: usb

usb:	../boot.img

../boot.img: init.cpi ../boot_img/* ../boot_img/*/*
	./make_boot_img.py

init.cpi: root/var/lib/rpm/Packages
	./make_initramfs.py

base.sqf: root/var/lib/rpm/Packages
	./make_squashfs.py base

root/var/lib/rpm/Packages: $(PSETS)
	./install_packages.py $(PSETS)

# vi: ft=make
