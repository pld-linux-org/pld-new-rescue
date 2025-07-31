
###########################################################
# Keep sane permissions for newly created files
umask 022

###########################################################
# Make sure the by-uuid symlink made by udev
# does not point to the 'Gap1/Gap2' partitions
# made by xorriso

cat > root/lib/udev/rules.d/70-pldnr-gap-partitions.rules << EOF
ENV{ID_PART_ENTRY_NAME}=="Gap[0-9]", OPTIONS+="link_priority=-100"
EOF

###########################################################
# set up the root password

if [ -n "$pldnr_hashed_root_password" ] ; then
	chroot root /usr/sbin/pwconv
	echo "root:$pldnr_hashed_root_password" | chroot root /usr/sbin/chpasswd -e
fi

###########################################################
# set up the systemd
chroot root /bin/systemctl preset-all

# default unit
ln -sf /lib/systemd/system/multi-user.target root/etc/systemd/system/default.target

# disable tty1 clearing
mkdir root/etc/systemd/system/getty@tty1.service.d/
cat > root/etc/systemd/system/getty@tty1.service.d/noclear.conf << EOF
[Service]
TTYVTDisallocate=no

EOF

# enable services
for service in network ; do
	chroot root /bin/systemctl enable "${service}".service || :
	# systemctl enable/disable is not reliable for chroot
#	if [ -L root/etc/systemd/system/getty.target.wants/${service}.service ] ; then
#		rm root/etc/systemd/system/getty.target.wants/${service}.service
#	fi
#	if [ -e root/etc/rc.d/init.d/service ] ; then
#		chroot root /sbin/chkconfig "${service}" on
#	fi
done

###########################################################
# set up the fstab

cat <<EOF >root/etc/fstab
none		/			tmpfs	defaults		0 0

UUID=$pldnr_cd_vol_id /media/pld-nr	iso9660	noauto,utf8,ro		0 0
UUID=$pldnr_efi_vol_id /boot/efi	vfat	noauto,utf8=true	0 0

none		/proc			proc	defaults,noauto,hidepid=2,gid=17	0 0
none		/sys			sysfs	defaults,noauto,gid=17	0 0
none		/sys/fs/cgroup		tmpfs	noauto,nosuid,nodev,noexec,mode=755	0 0
none		/proc/bus/usb		usbfs	defaults,noauto,devgid=78,devmode=0664	0 0
none		/dev/pts		devpts	gid=5,mode=620		0 0
none		/dev/shm		tmpfs	mode=1777,nosuid,nodev,noexec		0 0
EOF

echo "$pldnr_hostname" > root/etc/HOSTNAME
sed -i -e"s/^HOSTNAME=.*/HOSTNAME=$pldnr_hostname/" root/etc/sysconfig/network

absolute_root="$(readlink -f root)"

locales="$(echo $pldnr_locales|tr ',' ' ')"
lang="${pldnr_locales%%,*}"
build_locales="$(for loc in $locales ; do echo -n "${loc}.UTF-8/UTF-8 " ; done)" 

cat <<EOF >root/etc/sysconfig/i18n
LANG="${lang}.UTF-8"
SUPPORTED_LOCALES="${build_locales}"
EOF
chroot root /usr/bin/localedb-gen

rpm --root "$absolute_root" -e localedb-src


###########################################################
# workaround for slow shutdown

cat >>root/lib/systemd/system/user@.service <<'EOF'
# Apply same work around for user session killing
# (currently problem is that the kill issued by systemd --user is itself killed
# by systemd (PID1) before it can work which can lead to slow shutdowns
# http://thread.gmane.org/gmane.comp.sysutils.systemd.devel/16363
ExecStop=/bin/kill -TERM ${MAINPID}
KillSignal=SIGCONT
TimeoutStopSec=15
EOF

###########################################################
# add the third serial port to securetty

cat >> root/etc/securetty <<'EOF'
tts/2
ttyS2
EOF

###########################################################
# decrease console log level
# so the console is not spammed with audit messages

cat >> root/etc/sysctl.d/pldnr_printk.conf <<'EOF'
kernel.printk = 4	4	1	7
EOF
