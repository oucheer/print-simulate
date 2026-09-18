# -*- coding: utf-8 -*-
"""round 74: 
1) 简化轮询 patch（去掉每轮抓 PC 的额外 gdb，只留 patch 的 gdb，加速整体）
2) 突破后诊断：LPD 句柄(0x15cf0e58/0xe68/0xdf0)、线程 bt1 分布(timeout 120)、
   LPD/bind 相关线程、TCP/UNIX socket 列表

背景：round 73 证实轮询 patch 稳定解锁 print_info_status_init（main 进主循环），
但 TCP 监听仍为空。main 0x6a7f9c 无条件调 0x74f6dc，需验证其 pi_thread_create
是否成功（句柄 0x15cf0e58）以及 server_thread(0x74c604) 是否执行到 socket/bind/listen。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

# ---- 1) 简化轮询段 ----
start1 = 'sleep 10; for i in $(seq 1 30); do N=$(ls /proc/$MFP/task 2>/dev/null | wc -l); PC='
end1 = 'sleep 4; done; echo "--- ALIVE ---"'
i = s.index(start1)
j = s.index(end1, i) + len(end1)
poll_block = r'''sleep 10; for i in $(seq 1 30); do N=$(ls /proc/$MFP/task 2>/dev/null | wc -l); echo "--- POLL $i: N=$N ---"; if [ "$N" -eq 0 ]; then echo "POLL: mfp not ready yet"; sleep 4; continue; fi; if [ "$N" -gt 100 ]; then echo "POLL: passed print_info_status_init (N=$N)"; break; fi; gdb -p $MFP -batch -ex "set pagination off" -ex "set *(unsigned char*)(0xa91370+0x5c)=1" -ex "set *(unsigned int*)(0xa91370+0x7c)=1" -ex "set *(unsigned short*)(0xa91370+0x80)=1" -ex "set *(unsigned char*)(0xa91370+0x82)=1" -ex "detach" 2>&1 | tail -1; sleep 4; done; echo "--- ALIVE ---"'''
s = s[:i] + poll_block + s[j:]

# ---- 2) 增强诊断段 ----
start2 = 'echo "--- FUNC DIST ---"; timeout 30'
end2 = 'echo done'
i = s.index(start2)
j = s.index(end2, i) + len(end2)
diag_block = r'''echo "--- LPD HANDLES ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cf0e58" -ex "p/x *(long*)0x15cf0e68" -ex "p/x *(long*)0x15cf0df0" -ex "detach" 2>&1 | tail -8; echo "--- FUNC DIST ---"; timeout 120 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 1" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT=$(wc -l < /tmp/bt.txt)"; grep "^#0 " /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; echo "--- LPD/BIND THREADS ---"; grep -E "^Thread |0x74c[0-9a-f]{2}|0x74f[0-9a-f]{2}|0x74cd|bind|listen|accept|socket" /tmp/bt.txt | head -40; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -25; echo "--- UNIX ---"; cat /proc/net/unix 2>&1 | head -25; echo done'''
s = s[:i] + diag_block + s[j:]

open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
