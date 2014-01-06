
setup_ip () {
    # set up network using the Linux kernel 'ip' parameter (split into function arguments)

    # server_addr is global!
    local client_ip gw_ip netmask hostname device autoconf dns1 dns2

    server_addr=""
    eval "$(echo "$1" | awk -F: '{ print " \
client_ip="$1"\
server_addr="$2"\
gw_ip="$3"\
netmask="$4"\
hostname="$5"\
device="$6"\
autoconf="$7"\
dns1="$8"\
dns2="$9 }')"

    if [ -z "$client_ip" -a "(" "$autoconf" = "off" -o "$autoconf" = "none" ")" ] ; then
        return 1
    fi

    if [ -z "$device" ] ; then
        if [ -n "$c_pldnr_netdev" ] ; then
            if [ -e "/sys/class/net/$c_pldnr_netdev" ] ; then
                device="$c_pldnr_netdev"
            else
                local mac="$(echo "$c_pldnr_netdev" | tr "[[:upper:]]" "[[:lower:]]")"
                device="$(ip -o l | awk -F": " "/ether $mac / { print \$2 }")"
                if [ -z "$device" ] ; then
                    echo "Network device '$mac' not found"
                    return 1
                fi
            fi
        elif [ -e "/sys/class/net/eth0" ] ; then
            device="eth0"
        else
            echo "Network device not found"
            return 1
        fi
    fi

    if [ -n "$hostname" ] ; then
        hostname "$hostname"
    fi

    if [ "$autoconf" = "on" -o "$autoconf" = "any" -o "$autoconf" = "dhcp" -o -z "$client_ip" ] ; then
        mkdir -p /run/udhcpc
        cp /udhcpc.script /run/udhcpc/script
        chmod a+x /run/udhcpc/script
        cd /run/udhcpc
        udhcpc --now --pidfile /run/udhcpc/pid --script /run/udhcpc/script -O tftp --vendorclass "pld-new-rescue:$version" "$device"
        cd /
        if [ -z "$server_addr" -a -e /run/udhcpc/server_addr ] ; then
            server_addr=$(cat /run/udhcpc/server_addr)
        fi
    fi

    if [ -n "$client_ip" ] ; then
       local PREFIX
       if [ -n "$netmask" ] ; then
         eval "$(ipcalc -p "$client_ip" "$netmask")"
       else
         eval "$(ipcalc -p "$client_ip")"
       fi
       [ -n "$PREFIX" ] || PREFIX=24
       ip addr add "$client_ip/$PREFIX" dev "$netdev"
    fi
    if [ -n "$gw_ip" ] ; then
       ip route add dev "$netdev" default via "$gw_ip"   # onlink not supported by busybox :(
    fi
    if [ -n "$dns1" ] ; then
       echo "server $dns1" >> /etc/resolv.conf
    fi
    if [ -n "$dns2" ] ; then
       echo "server $dns2" >> /etc/resolv.conf
    fi
    return 0
}

setup_network () {

    if [ "$setup_network_done" = "yes" ] ; then
        if [ "$network_configured" = "yes" ] ; then
            return 0
        else
            return 1
        fi
    fi

    setup_network_done=yes
    keep_network="no"

    if [ -z "$c_ip" ] ; then
        c_ip="::::::on::"
    elif [ "${c_ip%:*}" == "${c_ip}" -a "${c_ip%.*}" == "${c_ip}" ] ; then
        c_ip="::::::$c_ip::"
    fi

    if setup_ip "$c_ip"; then
      network_configured="yes"
      return 0
    else
      network_configured="no"
      return 1
    fi
}

finish_network () {

    if [ "$keep_network" = "yes" ] ; then
        # keep network configuration running in case we use network resources
        [ -s /etc/resolv.conf ] && cp /etc/resolv.conf /root/etc/resolv.conf

        # disable wicd default wired profile
        # so it won't touch the connection
        cat > /root/etc/wicd/wired-settings.conf  <<EOF
[wired-default]
default = False
lastused = False
EOF
    else
        if [ -e /run/udhcpc/pid ] ; then
            # release the lease and clean up
            kill -USR2 $(cat /run/udhcpc/pid)
            usleep 500000
            kill $(cat /run/udhcpc/pid)
            ip link set $(cat /run/udhcpc/interface) down
            rm -rf /run/udhcpc
        fi
    fi
    rm -f /udhcpc.script

    # these files are included in squashfs, remove them from the rootfs
    cd /
    xargs rm -f < /_net.lst 2>/dev/null
    tac _net.lst | xargs rmdir --ignore-fail-on-non-empty 2>/dev/null
    rm /_net.lst
}

fetch_tftp_url () {
    local url="$1"
    local dest="$2"

    local host_path host path

    url="${url#tftp:}"
    local host_path="${url#//}"
    if [ "$host_path" != "$url" ] ; then
        # host provided
        host="${host_path%%/*}"
        path="${host_path#*/}"
    else
        host=""
        path="$url"
    fi
    if [ -z "$host" ] ; then
        if [ -z "$server_addr" ] ; then
            echo "Cannot fetch 'tftp:$url' – no server provided"
            return 1
        fi
        # take the one from ip= command line parameter
        # or from the DHCP response
        host="$server_addr"
    fi
    if [ -n "$host" -a -n "$path" ] ; then
        if tftp -l "$dest" -r "$path" -g "$host" ; then
            return 0
        else
            return 1
        fi
    else
        return 1
    fi
}

fetch_other_url () {
    local url="$1"
    local dest="$2"

    local tmp host_path host path

    tmp="${url#*:}"
    local host_path="${tmp#//}"
    if [ "$host_path" != "$tmp" ] ; then
        # host provided
        host="${host_path%%/*}"
        path="${host_path#*/}"
    else
        host=""
        path="$tmp"
    fi
    if [ -z "$host" ] ; then
        if [ -z "$server_addr" ] ; then
            echo "Cannot fetch '$url' – no server provided"
            return 1
        fi
        # set host to $server_addr
        url="${url%%:*}://$server_addr/${path#/}"
    fi
    if wget -O "$dest" "$url" ; then
        return 0
    else
        return 1
    fi
}

fetch_url () {
    local url="$1"
    local dest="$2"

    if [ "${url#tftp:}" != "$url" ] ; then
        if setup_network ; then
            fetch_tftp_url "$url" "$dest"
            return $?
        else
            echo "Cannot fetch '$url' – network not available" >&2
            return 1
        fi
    fi

    local tmp="${url%%/*}"
    if [ "${tmp#*:}" != "$tmp" -a "${tmp%%:*}" != "file" ] ; then
        # something:../something
        if setup_network ; then
            fetch_other_url "$url" "$dest"
            return $?
        else
            echo "Cannot fetch '$url' – network not available" >&2
            return 1
        fi
    fi

    url="${url#file:}"
    url="${url#//}"

    if [ -e "/root/$url" ] ; then
        cat "/root/$url" > "$dest"
        return $?
    else
        echo "Cannnot find '$url'" >&2
        return $?
    fi
}


# vi: ft=sh sw=4 sts=4 et
