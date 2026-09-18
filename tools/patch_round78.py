# -*- coding: utf-8 -*-
"""round 78: lo up 后验证 TCP 监听建立

round 77 证实 bind() error 根因 = lo 未 up（EADDRNOTAVAIL），ip link set lo up 后
bind/listen 成功。本轮：lo up + 轮询 patch 解锁 print_info_status_init + 突破后
检查 /proc/net/tcp（14279=0x37C7, 9120=0x23A0, 9130=0x23AA, 9132=0x23AC）、
LPD 句柄(0x15cf000e58)、线程分布、server_thread(0x74c604) 是否在 accept。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start = 'ip link set lo up 2>&1; ulimit -n 4096'
end = 'echo done'
i = s.index(start)
j = s.index(end, i) + len(end)

new_block = r'''ip link set lo up 2>&1; export LD_PRELOAD=/lib/libbinder_stub.so; ulimit -n 4096 2>/dev/null; /usr/bin/mfp.afx > /tmp/mfp.log 2>&1 & MFP=$!; echo "MFP_PID=$MFP"; unset LD_PRELOAD; sleep 10; for i in $(seq 1 30); do N=$(ls /proc/$MFP/task 2>/dev/null | wc -l); echo "--- POLL $i: N=$N ---"; if [ "$N" -eq 0 ]; then echo "POLL: mfp not ready yet"; sleep 4; continue; fi; if [ "$N" -gt 100 ]; then echo "POLL: passed print_info_status_init (N=$N)"; break; fi; gdb -p $MFP -batch -ex "set pagination off" -ex "set *(unsigned char*)(0xa91370+0x5c)=1" -ex "set *(unsigned int*)(0xa91370+0x7c)=1" -ex "set *(unsigned short*)(0xa91370+0x80)=1" -ex "set *(unsigned char*)(0xa91370+0x82)=1" -ex "detach" 2>&1 | tail -1; sleep 4; done; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; sleep 30; echo "--- LISTEN TCP ---"; cat /proc/net/tcp 2>&1 | head -30; echo "--- HANDLES ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cf000e58" -ex "p/x *(long*)0x15cf000e68" -ex "p/x *(long*)0x15cf000df0" -ex "detach" 2>&1 | tail -8; echo "--- MAIN BT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 8" -ex "detach" 2>&1 | tail -12; echo "--- FUNC DIST ---"; timeout 120 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 1" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT=$(wc -l < /tmp/bt.txt)"; grep "^#0" /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; echo "--- SERVER THREAD ---"; grep -E "0x74c[0-9a-f]{2}|accept|server_thread" /tmp/bt.txt | head -15; echo "--- LPD LOG ---"; grep -aE "pedk|bind|strat|server_thread" /tmp/mfp.log | tail -12; echo done'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
