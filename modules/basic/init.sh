
# Replace the built-in SSH authorized_keys file with the one
# from the boot medium

for _dir in /media/pld-nr-hd /media/pld-nr-cd ; do
    if [ -e $_dir/authorized_keys ] ; then
        mkdir -p /root/root/.ssh
        cat $_dir/authorized_keys > /root/root/.ssh/authorized_keys
        chmod 700 /root/root/.ssh
        chmod 644 /root/root/.ssh/authorized_keys
    fi
done

unset _dir

# vi: ft=sh et sw=4 sts=4
