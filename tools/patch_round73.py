# -*- coding: utf-8 -*-
"""round 73: 轮询式 outside_info patch，消除 print_info_status_init 双态竞态

背景：round 72 证实低状态 run 的 main 卡在 print_info_status_init (0x5ef110)
无限等 outside_info（pi_msleep(500) 循环）；单次 patch 若时机过早（main 尚未
进入等待循环），outside_info 会在 print_info_status_init 初始化时被清零覆盖。

方案：每 ~9s 检查一次线程数 N；若 N <= 100（未越过打印初始化）则重新写
outside_info 4 字段 = 1（幂等）。一旦 N > 100 说明 main 已越过打印初始化，
停止轮询。最多 30 次（约 280s 上限）。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = 'sleep 60; echo "--- GDB PATCH ---"'
end_marker = 'sleep 45; echo "--- ALIVE ---"'
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''sleep 10; for i in $(seq 1 30); do N=$(ls /proc/$MFP/task 2>/dev/null | wc -l); PC=$(gdb -p $MFP -batch -ex "set pagination off" -ex "thread 1" -ex "p/x \$pc" -ex "detach" 2>&1 | grep -oE "0x[0-9a-f]+" | tail -1); echo "--- POLL $i: N=$N PC=$PC ---"; if [ "$N" -eq 0 ]; then echo "POLL: mfp not ready yet"; sleep 4; continue; fi; if [ "$N" -gt 100 ]; then echo "POLL: passed print_info_status_init (N=$N)"; break; fi; gdb -p $MFP -batch -ex "set pagination off" -ex "set *(unsigned char*)(0xa91370+0x5c)=1" -ex "set *(unsigned int*)(0xa91370+0x7c)=1" -ex "set *(unsigned short*)(0xa91370+0x80)=1" -ex "set *(unsigned char*)(0xa91370+0x82)=1" -ex "detach" 2>&1 | tail -1; sleep 4; done; echo "--- ALIVE ---"'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
