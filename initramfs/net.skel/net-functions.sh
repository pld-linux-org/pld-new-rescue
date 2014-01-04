
setup_ip () {
    # set up network using the Linux kernel 'ip' parameter (split into function arguments)

    # server_ip is global!
    local client_ip gw_ip netmask hostname device autoconf dns1 dns2

    eval "$(echo "$1" | awk -F: '{ print " \
client_ip="$1"\
server_ip="$2"\
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
        chmod a+x /udhcpc.script
        udhcpc --quit --now --script /udhcpc.script "$device"
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

# vi: ft=sh sw=4 sts=4 et
