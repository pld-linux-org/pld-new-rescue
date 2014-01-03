
# Replace the built-in SSH authorized_keys file with the one
# from the boot medium

if [ -e /media/pld-nr/authorized_keys ] ; then
    mkdir -p /root/root/.ssh
    cat /media/pld-nr/authorized_keys > /root/root/.ssh/authorized_keys
    chmod 700 /root/root/.ssh
    chmod 644 /root/root/.ssh/authorized_keys
fi

# enable password authentication forr SSH

if [ "$c_pldnr_sshpw" = "yes" ] ; then

    sed -i -e's/^PermitRootLogin.*/PermitRootLogin yes/;s/^PasswordAuthentication.*/PasswordAuthentication yes/;s/^ChallengeResponseAuthentication.*/ChallengeResponseAuthentication yes/' \
        /root/etc/ssh/sshd_config
fi

# vi: ft=sh et sw=4 sts=4
