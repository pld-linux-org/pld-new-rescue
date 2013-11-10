
mount_media() {

    echo "Mounting the boot image"
    modprobe vfat
    modprobe nls_cp437
    modprobe nls_iso8859-1
    mkdir -p /root/media/pld-nr-hd
    /bin/mount -t vfat -outf8=true,codepage=437 UUID="$hd_vol_id" /root/media/pld-nr-hd || :

    echo "Attempting to mount the boot CD"
    modprobe isofs
    mkdir -p /root/media/pld-nr-cd
    /bin/mount -t iso9660 -outf8 UUID="$cd_vol_id" /root/media/pld-nr-cd 2>/dev/null || :

    ln -sf /root/media /media
}

umount_media() {

    if mountpoint -q /root/media/pld-nr-hd ; then
        if umount /root/media/pld-nr-hd 2>/dev/null ; then
            echo "Boot image unmounted"
        else
            echo "Boot image in use, keeping it mounted"
        fi
    fi
    if mountpoint -q /root/media/pld-nr-cd ; then
        if umount /root/media/pld-nr-cd 2>/dev/null ; then
            echo "Boot CD unmounted"
        else
            echo "Boot CD in use, keeping it mounted"
        fi
    fi
    rm /media
}

mount_aufs() {

    for dir in var ; do
        if [ -d /$dir ] ;  then
            cp -a /$dir /root/$dir
        else
            mkdir -p /root/$dir
        fi
    done

    for dir in boot usr sbin lib lib64 etc bin opt root ; do
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
        echo "Module '$module' not found"
        return 1
    fi

    lodev=$(/sbin/losetup -o $offset --find --show $sqf)
    mkdir -p "/.rcd/m/${module}"
    mount -t squashfs "$lodev" "/.rcd/m/${module}"

    for dir in var ; do
        if [ -d /.rcd/m/${module}/$dir ] ;  then
            cd /.rcd/m/${module}/$dir
            find | cpio -p /root/$dir
            cd /
        fi
    done

    for dir in boot usr sbin lib lib64 etc bin opt ; do
        if [ -d /.rcd/m/${module}/$dir ] ; then
            mount -o remount,add:1:/.rcd/m/${module}/$dir=rr /root/$dir
        fi
    done
}

# vi: ft=sh sw=4 sts=4 et
