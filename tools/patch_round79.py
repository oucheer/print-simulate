# -*- coding: utf-8 -*-
"""round 79: 保持 mfp 存活 + 修正句柄(0x15cfe58) + port913x 线程 bt + LPD 14279 验证

round 78 已证 LPD(127.0.0.1:14279) LISTEN 就绪、server_thread 在 accept。
本轮：1) 诊断段改修正句柄地址 2) 抓 port913x 线程等待点 3) 不 kill mfp，
SIMBOOT 结束后 QEMU 保持运行，hostfwd 有效，可从 Windows 侧测试 14279 连接。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start = 'echo "--- ALIVE ---"; ls /proc/$MFP/task'
end = 'echo done'
i = s.index(start)
j = s.index(end, i) + len(end)

new_block = r'''echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; sleep 30; echo "--- LISTEN TCP ---"; cat /proc/net/tcp 2>&1 | head -30; echo "--- HANDLES(corrected) ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cfe58" -ex "p/x *(long*)0x15cfe68" -ex "p/x *(long*)0x15cfdf0" -ex "detach" 2>&1 | tail -8; echo "--- MAIN BT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 8" -ex "detach" 2>&1 | tail -12; echo "--- FUNC DIST ---"; timeout 120 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 1" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT=$(wc -l < /tmp/bt.txt)"; grep "^#0" /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; echo "--- PORT913X THREADS ---"; grep -E "0x67b98c|0x67bc2c|0x67c[0-9a-f]{2}|pi_sem_wait" /tmp/bt.txt | head -20; echo "--- SERVER THREAD ---"; grep -E "0x74c[0-9a-f]{2}|accept" /tmp/bt.txt | head -10; echo "--- LPD LOG ---"; grep -aE "pedk|bind|strat|server_thread|port91" /tmp/mfp.log | tail -15; echo "KEEPING MFP ALIVE (pid $MFP)"'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
