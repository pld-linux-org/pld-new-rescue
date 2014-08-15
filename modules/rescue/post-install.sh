
###########################################################
# Disable default rc-scripts network config
# wicd does much better job here

cat > root/etc/sysconfig/interfaces/ifcfg-eth0 << EOF
DEVICE=eth0

# do not configure this interface via PLD rc-scripts
# the wicd network manager does much better job
# for temporary connections
ONBOOT=no

BOOTPROTO=dhcp
EOF

cp root/etc/wicd/dhclient.conf.template{.default,}
echo "send vendor-class-identifier \"pld-new-rescue:$pldnr_version\";" >> root/etc/wicd/dhclient.conf.template

cat > root/etc/wicd/manager-settings.conf <<EOF
[Settings]
auto_reconnect = True
wired_connect_mode = 0
dhcp_client = 1
prefer_wired = True
EOF

# make the default wired profile active
# so it automatically connects on boot
cat > root/etc/wicd/wired-settings.conf  <<EOF
[wired-default]
default = True
lastused = True
EOF

###########################################################
# set up the systemd

# disable services
for service in \
		arpwatch blkmapd dhcp-relay dhcpd dhcpd6 dnsmasq \
		gssd httptunnel idmapd ipmievd iscsi-devices mdadm \
		nfsd nfsd-exportfs nfsd-mountd nfslock nut-driver nut-monitor \
		nut-server p0f pure-ftpd racoon rdate rpcbind rstatd rusersd \
		rwhod smartd snmpd svcgssd tftpd-hpa tinyproxy ups upsmon \
		vtund zfs-fuse \
	; do
	chroot root /bin/systemctl disable ${service}.service || :

	# systemctl sometimes fails to properly chkconfig off
	if [ -e root/etc/rc.d/init.d/"$service" ] ; then
		chroot root chkconfig --level=12345 "$service" off || :
	fi
done

###########################################################
# disable telnetd
rm -f root/etc/sysconfig/rc-inetd/telnetd

###########################################################
# disable useless cron jobs

for crontab in logcheck scdp uucp ; do
	sed -i -e's/^/#/' root/etc/cron.d/$crontab
done
chmod 0 root/etc/cron.daily/rdate
chmod 0 root/etc/cron.daily/man-db.cron
chmod 0 root/etc/cron.weekly/chkrootkit-check
