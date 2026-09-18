# -*- coding: utf-8 -*-
"""round 72: 抓 main bt（无论高低状态），确定 mfp 卡点/分叉点"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- MAIN BT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread 1" -ex "bt 10" -ex "detach" 2>&1 | tail -14; echo "--- FUNC DIST ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 2" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT=$(wc -l < /tmp/bt.txt)"; grep "^#0 " /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -25; echo "--- MFP LOG TAIL ---"; tail -c 30000 /tmp/mfp.log 2>&1 | grep -av "_wait_for_peer" | tail -15; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
