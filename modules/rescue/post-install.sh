
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

