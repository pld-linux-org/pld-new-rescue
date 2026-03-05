
###########################################################
# NetworkManager replaces rc-scripts network management
chroot root /bin/systemctl disable network.service || :
chroot root /bin/systemctl enable NetworkManager.service || :

# DHCP vendor class identifier for network identification
mkdir -p root/etc/NetworkManager/conf.d
cat > root/etc/NetworkManager/conf.d/pld-nr.conf <<EOF
[connection-pld-nr-defaults]
match-device=type:ethernet
ipv4.dhcp-vendor-class-identifier=pld-new-rescue:$pldnr_version
EOF

###########################################################
# set up the systemd

# disable services
for service in \
		arpwatch blkmapd dhcp-relay dhcpd dhcpd6 dnsmasq \
		gssd httptunnel idmapd ipmievd iscsi iscsid mdadm \
		mdmonitor cronjob-mdadm mdmon@ mdadm-last-resort@ mdadm-grow-continue@ \
		nfsd nfsd-exportfs nfsd-mountd nfslock nut-driver nut-monitor \
		nut-server p0f pure-ftpd racoon rdate rpcbind rstatd rusersd \
		rwhod smartd snmpd svcgssd tftpd-hpa tinyproxy ups upsmon \
		vtund zfs-fuse \
	; do
	chroot root /bin/systemctl disable ${service}.service || :
	# static services can only be masked
	if [ "$(chroot root /bin/systemctl is-enabled ${service}.service 2> /dev/null)" = "static" ]; then
		chroot root /bin/systemctl mask ${service}.service || :
	fi

	# systemctl sometimes fails to properly chkconfig off
	if [ -e root/etc/rc.d/init.d/"$service" ] ; then
		chroot root chkconfig --level=12345 "$service" off || :
	fi
done

if [ -f root/etc/mdadm.conf ]; then
cat >> root/etc/mdadm.conf  <<EOF

# prevent mdadm from auto assembling arrays and potentially damaging these
AUTO -all
EOF
fi

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
