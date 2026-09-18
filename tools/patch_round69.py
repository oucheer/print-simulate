# -*- coding: utf-8 -*-
"""round 69: 抓 main 线程 bt（直接串口输出），定位 main 卡点"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- MAIN BT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 12" -ex "detach" 2>&1 | tail -22; echo "--- MAIN TASK STAT ---"; cat /proc/$MFP/task/$MFP/stat 2>/dev/null | awk "{print \\$3, \\$29, \\$30}"; echo "--- FUNC DIST ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 2" -ex "detach" > /tmp/bt.txt 2>&1; grep "^#0 " /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; sleep 30; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
