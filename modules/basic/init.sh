
# Replace the built-in SSH authorized_keys file with the one
# from the boot medium or the URL provided in pldnr.keys option
if [ -n "$c_pldnr_keys" ] ; then
    if fetch_url "$c_pldnr_keys" /authorized_keys ; then
        echo "# Authorized SSH keys from '$c_pldnr_keys' (supplied on the boot command line)" > /root/root/.ssh/authorized_keys
        cat /authorized_keys >> /root/root/.ssh/authorized_keys
        chmod 700 /root/root/.ssh
        chmod 644 /root/root/.ssh/authorized_keys
        rm /authorized_keys
    fi
elif [ -e /media/pld-nr/authorized_keys ] ; then
    mkdir -p /root/root/.ssh
    echo "# Authorized SSH keys from 'authorized_keys' on PLD NR boot ISO" > /root/root/.ssh/authorized_keys
    cat /media/pld-nr/authorized_keys >> /root/root/.ssh/authorized_keys
    chmod 700 /root/root/.ssh
    chmod 644 /root/root/.ssh/authorized_keys
fi

# enable password authentication forr SSH

if [ "$c_pldnr_sshpw" = "yes" ] ; then

    sed -i -e's/^PermitRootLogin.*/PermitRootLogin yes/;s/^PasswordAuthentication.*/PasswordAuthentication yes/;s/^ChallengeResponseAuthentication.*/ChallengeResponseAuthentication yes/' \
        /root/etc/ssh/sshd_config
fi

# enable autologin on tty1

if [ "$c_pldnr_autologin" = "yes" ] ; then

    cat >> /root/etc/systemd/system/getty@tty1.service.d/noclear.conf << EOF
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I '$TERM'
EOF
fi
# vi: ft=sh et sw=4 sts=4
