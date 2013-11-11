
#######################################################3
# config root shell

chroot root chsh -s /bin/bash root
mkdir -p root/root
cp -au root/etc/skel/.bash* root/root/

#######################################################3
# config sshd

# embed authorized_keys file
if [ -s ../authorized_keys ] ; then
        mkdir -p root/root/.ssh
        cat ../authorized_keys > root/root/.ssh/authorized_keys
        chmod 700 root/root/.ssh
        chmod 644 root/root/.ssh/authorized_keys
fi

# write config file
cat <<EOF >root/etc/ssh/sshd_config
PermitRootLogin without-password
AuthorizedKeysFile	.ssh/authorized_keys
IgnoreRhosts yes
PasswordAuthentication no
ChallengeResponseAuthentication no
PermitEmptyPasswords no
UsePAM yes
AllowAgentForwarding yes
AllowTcpForwarding yes
X11Forwarding yes
UsePrivilegeSeparation sandbox
AcceptEnv LANG LC_* LANGUAGE TZ GIT_AUTHOR_* GIT_COMMITTER_*
Subsystem	sftp	/usr/lib/openssh/sftp-server
EOF

#######################################################3
# config syslog

cat <<EOF >root/etc/syslog-ng/syslog-ng.conf
@version: 3.3

options {
        chain_hostnames(no);
        flush_lines(0);
        owner(root);
        group(logs);
        perm(0640);
        create_dirs(yes);
        dir_owner(root);
        dir_group(logs);
        dir_perm(0750);
        stats_freq(3600);
        time_reopen(10);
        time_reap(360);
        mark_freq(600);
        log_fifo_size(100000);
};

source s_sys {
	file ("/proc/kmsg" program_override("kernel: "));
	unix-dgram("/run/systemd/journal/syslog");
	internal();
};

destination d_syslog    { file("/var/log/syslog"); };
destination d_console   { usertty("root"); };
destination d_console_all       { file("/dev/tty12"); };

filter p_emergency      { level(emerg); };

log { source(s_sys);                      destination(d_console_all); };
log { source(s_sys); filter(p_emergency); destination(d_console); };
log { source(s_sys);                      destination(d_syslog); };
EOF
