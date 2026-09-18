# -*- coding: utf-8 -*-
"""round 68: 强制 call 0x74f6dc 启动 LPD 监听 + 修正 main bt 抓取"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- LPD HANDLE ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cf0e58" -ex "detach" 2>&1 | tail -3; echo "--- CALL LPD START ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set confirm off" -ex "call (void)0x74f6dc()" -ex "detach" 2>&1 | tail -6; sleep 20; echo "--- LISTEN 1 ---"; cat /proc/net/tcp 2>&1 | head -20; echo "--- ALIVE 2 ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- LPD HANDLE 2 ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cf0e58" -ex "detach" 2>&1 | tail -3; echo "--- MAIN BT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 8" -ex "detach" > /tmp/bt.txt 2>&1; grep -A9 "^Thread 1 (" /tmp/bt.txt | head -22; sleep 60; echo "--- FINAL LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo "--- FINAL ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
