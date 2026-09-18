# -*- coding: utf-8 -*-
"""round 76: strace 抓 bind 失败 errno

round 75 证实 server_thread 创建成功但 bind(127.0.0.1:14279) 失败（bind() error），
监听线程退出导致无 TCP 监听。binder_stub 不拦截 bind，需抓真实 errno。

用 strace（rootfs 自带）从 mfp 启动即跟随 trace socket/bind/listen/accept/connect。
bind 发生在 pedk_mgr_prolog（早于 print_info_status_init 卡点），无需 gdb 轮询，
strace 与 gdb 的 ptrace 冲突也避免了。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start = 'export LD_PRELOAD=/lib/libbinder_stub.so; ulimit -n 4096 2>/dev/null; /usr/bin/mfp.afx'
end = 'echo done'
i = s.index(start)
j = s.index(end, i) + len(end)

new_block = r'''ip link set lo up 2>&1; export LD_PRELOAD=/lib/libbinder_stub.so; ulimit -n 4096 2>/dev/null; /usr/bin/strace -f -e trace=socket,bind,listen,accept,connect,getsockname -s 80 -o /tmp/strace.log /usr/bin/mfp.afx > /tmp/mfp.log 2>&1 & MFP=$!; echo "MFP_PID=$MFP (strace parent)"; unset LD_PRELOAD; sleep 600; echo "--- KILL ---"; kill -9 $MFP 2>/dev/null; sleep 2; echo "--- BIND/SOCKET ---"; grep -aE "bind\(|socket\(|listen\(|accept|connect\(" /tmp/strace.log 2>&1 | head -40; echo "--- ERRNO ---"; grep -aE "= -1" /tmp/strace.log 2>&1 | head -20; echo "--- MFP LOG pedk ---"; grep -aE "pedk|bind|server_thread|strat" /tmp/mfp.log 2>&1 | tail -15; echo done'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
