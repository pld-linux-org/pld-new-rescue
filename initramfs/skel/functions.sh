
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
        if /sbin/blkid -U "$cd_vol_id" ; then
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
        ls -l /root/media/pld-nr
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
    rm /media
}

mount_aufs() {

    for dir in boot usr sbin lib lib64 etc bin opt root var ; do
        mkdir -p /root/.rw/$dir /root/$dir
        if [ -d /$dir -a "$dir" != "root" ] ; then
            mount -t aufs -o dirs=/root/.rw/$dir=rw:/$dir=ro none /root/$dir
        else
            mount -t aufs -o dirs=/root/.rw/$dir=rw none /root/$dir
        fi
    done
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

# vi: ft=sh sw=4 sts=4 et
