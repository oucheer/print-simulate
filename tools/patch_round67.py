# -*- coding: utf-8 -*-
"""round 67: 诊断 main 卡点——LPD 线程句柄/主线程 PC/线程分布"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- LPD HANDLE ---"; dd if=/proc/$MFP/mem bs=1 count=8 skip=$((0x15cf0e58)) 2>/dev/null | od -An -tx8; echo "--- BT2 ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 6" -ex "thread apply all bt 2" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT_LINES=$(wc -l < /tmp/bt.txt)"; echo "--- MAIN BT ---"; grep -A7 "^Thread 1" /tmp/bt.txt | head -24; echo "--- FUNC DIST ---"; grep -E "  #0 " /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; echo "--- MFP LOG TAIL ---"; tail -c 20000 /tmp/mfp.log 2>&1 | tail -12; sleep 30; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
