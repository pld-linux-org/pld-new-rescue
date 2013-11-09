
if [ -n "$pldnr_hashed_root_password" ] ; then
	chroot root /usr/sbin/pwconv
	echo "root:$pldnr_hashed_root_password" | chroot root /usr/sbin/chpasswd -e
fi

ln -sf /lib/systemd/system/multi-user.target root/etc/systemd/system/default.target

cat <<EOF >root/etc/fstab
none		/			tmpfs	defaults		0 0

UUID=$pldnr_hd_vol_id /media/pld-nr-hd	vfat	noauto			0 0
UUID=$pldnr_cd_vol_id /media/pld-nr-cd	iso9660	noauto,ro		0 0

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

