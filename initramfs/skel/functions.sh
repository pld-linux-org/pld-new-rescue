
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
