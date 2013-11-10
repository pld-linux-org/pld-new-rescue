
###########################################################
# set up the systemd

# disable services
for service in \
		arpwatch blkmapd dhcp-relay dhcpd dhcpd6 dnsmasq \
		gssd httptunnel idmapd ipmievd iscsi-devices mdadm \
		nfsd-mountd nfslock nut-driver nut-monitor nut-server \
		p0f pure-ftpd racoon rdate rpcbind rstatd rusersd rwhod \
		smartd snmpd svcgssd tftpd-hpa tinyproxy ups upsmon \
		vtund zfs-fuse \
	; do
	chroot root /bin/systemctl disable ${service}.service || :

	# systemctl sometimes fails to properly chkconfig off
	if [ -e root/etc/rc.d/init.d/"$service" ] ; then
		chroot root chkconfig --level=12345 "$service" off || :
	fi
done

