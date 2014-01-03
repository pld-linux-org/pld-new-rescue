
parse_cmdline() {
    local name
    local value

    while [ -n "$1" ] ; do
        o_name="${1%%=*}"
        name="$(echo -n $o_name | tr " .'\"\\\`\\\\\\n-" "________")"
        value="${1#*=}"
        value="$(echo -n $value | tr "'\\\\\\n" "___")"
        if [ "$1" = "$o_name" ] ; then
            echo "c_$name=yes"
        else
            echo "c_$name='$value'"
        fi
        shift
    done
}

mount_media() {

    local boot_dev=""

    if [ "$c_pldnr_nomedia" = "yes" ] ; then
        return 0
    fi

    for i in 1 2 3 4 5 6 7 8 9 10; do
        if /sbin/blkid -U "$cd_vol_id" >/dev/null ; then
            break
        fi
        echo "Waiting for the boot media to appear..."
        sleep 1
    done

    echo "Attempting to mount the boot file system"
    modprobe isofs
    modprobe nls_utf8
    mkdir -p /root/media/pld-nr
    if /bin/mount -t iso9660 -outf8 UUID="$cd_vol_id" /root/media/pld-nr 2>/dev/null ; then
        echo "PLD New Rescue medium found"
    fi
}

umount_media() {

    if mountpoint -q /root/media/pld-nr ; then
        if umount /root/media/pld-nr 2>/dev/null ; then
            echo "Boot medium unmounted"
        else
            echo "Boot medium in use, keeping it mounted"
        fi
    fi
}

mount_aufs() {

    mkdir -p /root/.rw/etc/systemd/system

    echo "" > /fstab-add
    echo "# PLD NR aufs filesystems (auto-generated)" >> /fstab-add

    for dir in boot usr sbin lib lib64 etc bin opt root var ; do
        mkdir -p /root/.rw/$dir /root/$dir
        if [ -d /$dir -a "$dir" != "root" ] ; then
            options="dirs=/root/.rw/$dir=rw:/$dir=ro"
        else
            options="dirs=/root/.rw/$dir=rw"
        fi
        mount -t aufs -o $options none /root/$dir
        echo "none /$dir aufs $options 0 0" >> /fstab-add
        cat > /root/.rw/etc/systemd/system/${dir}.mount <<EOF
[Unit]
Description=/$dir mount
DefaultDependencies=false

[Mount]
What=none
Where=/$dir
Type=aufs
Options=$options
EOF
    done
    echo "" >> /fstab-add
}

load_module() {
    local module="$1"
    local lodev
    local offset=0
    local sqf=/.rcd/modules/${module}.sqf

    if [ ! -e "$sqf" ] ; then
        name_len=$(expr length $module)
        offset=$(( ((118 + $name_len)/4) * 4 ))
        sqf="/root/media/pld-nr$prefix/${module}.cpi"
    fi

    if [ ! -e "$sqf" ] ; then
        echo "Module '$module' not found"
        return 1
    fi

    echo "Activating '$module' module"

    lodev=$(/sbin/losetup -o $offset --find --show $sqf)
    mkdir -p "/.rcd/m/${module}"
    mount -t squashfs "$lodev" "/.rcd/m/${module}"

    for dir in boot usr sbin lib lib64 etc bin opt root var ; do
        if [ -d /.rcd/m/${module}/$dir ] ; then
            mount -o remount,add:1:/.rcd/m/${module}/$dir=rr /root/$dir
        fi
    done

    if [ -f /.rcd/modules/${module}.init ] ; then
        . /.rcd/modules/${module}.init
    fi
}

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
