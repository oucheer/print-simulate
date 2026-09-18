# -*- coding: utf-8 -*-
"""round 70: mfp.log 全量尾部 + server_thread 状态检查"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- MFP LOG LAST 40 ---"; tail -c 400000 /tmp/mfp.log 2>&1 | tail -40; echo "--- MFP LOG NET ---"; tail -c 400000 /tmp/mfp.log 2>&1 | grep -aiE "server_thread|pedk|9130|9120|lpd|listen|bind|fail|error|ibc" | tail -30; echo "--- BT ALL ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 3" -ex "detach" > /tmp/bt.txt 2>&1; echo "THREADS=$(grep -c Thread /tmp/bt.txt)"; grep -aiE "server_thread|pedk|74c604|accept|listen" /tmp/bt.txt | head -12; sleep 30; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
