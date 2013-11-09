
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
