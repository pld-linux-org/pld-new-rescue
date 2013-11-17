
# Replace the built-in SSH authorized_keys file with the one
# from the boot medium

if [ -e /media/pld-nr/authorized_keys ] ; then
    mkdir -p /root/root/.ssh
    cat /media/pld-nr/authorized_keys > /root/root/.ssh/authorized_keys
    chmod 700 /root/root/.ssh
    chmod 644 /root/root/.ssh/authorized_keys
fi

# vi: ft=sh et sw=4 sts=4
