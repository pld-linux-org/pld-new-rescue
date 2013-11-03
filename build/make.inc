

include ../build.conf

LABEL=PLDNR_$(shell echo $(VERSION) | tr . _)
	
PSETS=../packages/base.pset

.PHONY: usb

usb:	../boot.img

../boot.img: initramfs.img base.sqf

initramfs.img: root/var/lib/rpm/Packages
	./make_initramfs.py

base.sqf: root/var/lib/rpm/Packages
	./make_squashfs.py base

root/var/lib/rpm/Packages: $(PSETS)
	./install_packages.py $(PSETS)

# vi: ft=make
