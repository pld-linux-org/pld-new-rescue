
include make.vars

usb:	../pld-nr-$(BITS).img

cd:	../pld-nr-$(BITS).iso

.PHONY: usb cd clean maintaner-clean

ifeq ($(MAKE_VARS_INCLUDED),yes)

../pld-nr-$(BITS).img: init.cpi $(MODULE_FILES) ../boot_img/* ../boot_img/*/*
	./make_boot_img.py $@

init.cpi base.lst: base.full-lst ../initramfs/files.list ../initramfs/skel/*
	./make_initramfs.py

%.cpi: %.sqf
	echo $< | cpio -o -H newc -F $@

%.sqf: %.lst
	./make_module.py $*

$(PSET_LST_FILES): poldek.conf
	./install_packages.py

poldek.conf: ../modules/poldek.conf ../build.conf
	./pld_nr_buildconf.py --substitute < ../modules/poldek.conf > poldek.conf

clean:
	-rm -rf root
	-rm -rf *.lst *.full-lst gen_init_cpio.list *.exclude
	-rm -rf *.cpi *.sqf *.img
	-rm -rf poldek.conf grub*.cfg

endif

make.vars: ../build.conf ./pld_nr_buildconf.py
	./pld_nr_buildconf.py --make-vars > make.vars

make.deps: ../build.conf ./pld_nr_buildconf.py
	./pld_nr_buildconf.py --make-deps > make.deps

include make.deps

# vi: ft=make
