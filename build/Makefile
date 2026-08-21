
export ARCH=

# Verbose build: 'make V=1' switches every build script to DEBUG-level logging.
# Exported, not passed per recipe, so scripts run by hand and recipes added
# later are covered too; get_default_log_level() in pld_nr_buildconf.py decides.
ifneq ($(V),)
export PLD_NR_DEBUG := $(V)
endif

include make.vars

.PHONY: image

image:	../pld-nr-$(BITS).iso
	echo ; echo "$$(readlink -f $<) image built ($$(($$(stat --printf="%s" $<)/1048576)) MiB)" ; echo

.PHONY: bindist clean

ifeq ($(MAKE_VARS_INCLUDED),yes)

../pld-nr-$(BITS).iso: ./make_iso_img.py ./fix_gpt.py uuids $(INITRAMFS_FILES) $(MODULE_FILES) efi.img $(PC_GRUB_IMAGES) $(NET_GRUB_IMAGES) $(FONT_FILE) ../iso_templ/* ../iso_templ/*/* ../iso_templ/*/*/*
	./make_iso_img.py $@
	./fix_gpt.py --write $@

efi.img: ./make_efi_img.py $(EFI_GRUB_IMAGES) ../efi_templ/*
	./make_efi_img.py $@

boot.img: grub-i386-pc.img /lib/grub/i386-pc/cdboot.img
	cat /lib/grub/i386-pc/cdboot.img grub-i386-pc.img > $@

netboot.pxe: ./make_grub_img.py /lib/grub/i386-pc
	./make_grub_img.py --pxe i386-pc $@

net_ia32.efi: ./make_grub_img.py /lib/grub/i386-efi
	./make_grub_img.py --pxe i386-efi $@

net_x64.efi: ./make_grub_img.py /lib/grub/x86_64-efi
	./make_grub_img.py --pxe x86_64-efi $@

.INTERMEDIATE: boot.img

font.pf2: /usr/share/fonts/TTF/DejaVuSansMono.ttf
	grub-mkfont --output $@ $<


grub-%.img: ./make_grub_img.py uuids /lib/grub/%
	./make_grub_img.py $* $@

_init.cpi base.lst _init.lst: ./make_initramfs.py uuids base.full-lst ../initramfs/init.files ../initramfs/init.skel/*
	./make_initramfs.py --substract-contents base.full-lst base.lst init

_net.cpi _net.lst: ./make_initramfs.py _init.lst ../initramfs/net.files ../initramfs/net.skel/*
	./make_initramfs.py --exclude=_init.lst net

%.cpi: %.sqf
	echo $< | cpio -o -H newc -F $@

%.sqf: %.lst ./make_module.py
	./make_module.py $*

$(PSET_LST_FILES): ./install_packages.py poldek.conf
	./install_packages.py

poldek.conf: ./pld_nr_buildconf.py ../modules/poldek.conf ../build.conf
	./pld_nr_buildconf.py --substitute < ../modules/poldek.conf > poldek.conf

bindist: image
	mkdir -p ../dist
	ln -f ../pld-nr-$(BITS).iso ../dist/pld-new-rescue-$(VERSION)-$(BITS)bit.iso
	ln -f ../pld-nr-$(BITS).packages ../dist/pld-new-rescue-$(VERSION)-$(BITS)bit-packages.txt
	rm -f ../dist/pld-new-rescue-$(VERSION)-$(ARCH)-extra_packages.tar
	if [ "$$(echo ../extra_packages/th-current/$(ARCH)/*.rpm)" != "../extra_packages/th-current/$(ARCH)/*.rpm" ] ; then \
		cd .. && \
		tar cvf dist/pld-new-rescue-$(VERSION)-$(ARCH)-extra_packages.tar extra_packages/th-current/$(ARCH)/*.rpm ; \
	fi
endif

clean:
	-if $(SUDO) mountpoint -q efi_mnt ; then $(SUDO) umount efi_mnt ; fi
	-$(SUDO) rm -rf --one-file-system root
	-rm -rf *.lst *.full-lst *.pkgs *gen_init_cpio.list *.exclude
	-rm -rf *.cpi *.sqf *.img
	-rm -rf netboot.pxe net_*.efi
	-rm -rf poldek.conf grub*.cfg
	-rm -f font.pf2
	-rm -f make.vars make.deps
	-rm -f pld-nr-net.env uuids
	-rmdir efi_mnt
	-$(SUDO) rm -rf cache __pycache__

make.vars: ../build.conf ./pld_nr_buildconf.py /usr/bin/python3
	./pld_nr_buildconf.py --verify --make-vars > make.vars

# no prerequisites on purpose: build UUIDs must survive a rebuild, only
# 'make clean' issues new ones
uuids:
	./pld_nr_buildconf.py --gen-uuids > /dev/null

make.deps: make.vars /usr/bin/python3
	./pld_nr_buildconf.py --make-deps > make.deps

.DELETE_ON_ERROR:

/usr/bin/python3:
	echo "ERROR: python3 interpreter missing"
	exit 1

include make.deps

# vi: ft=make
