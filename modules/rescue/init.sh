find_boot_netdev 2>/dev/null

if [ -n "$network_device" ] ; then
	echo "wired_interface = $network_device" >> /root/etc/wicd/manager-settings.conf
fi
