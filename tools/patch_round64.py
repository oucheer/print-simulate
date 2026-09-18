# -*- coding: utf-8 -*-
"""round 64: 抓全线程名/main线程卡点/plog网络日志，判断 TCP 监听由谁触发"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -8; sleep 20;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -8; sleep 20; echo "--- CHECK ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- BT DUMP ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 4" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT_LINES=$(wc -l < /tmp/bt.txt)"; echo "--- THREAD NAMES ---"; grep -oE "caller=0x[0-9a-f]+ <[^>]+>" /tmp/bt.txt | sort | uniq -c | sort -rn | head -40; echo "--- MAIN BT ---"; awk "/^Thread 1 /{f=1} f{print; c++} c>12{exit}" /tmp/bt.txt; echo "--- UNIX SOCKETS ---"; cat /proc/net/unix 2>&1 | head -30; echo "--- PLOG DIR ---"; ls -la /tslog/ 2>&1 | head -20; echo "--- PLOG NET ---"; tail -c 200000 /tslog/*.log 2>/dev/null | grep -aiE "listen|bind|9130|9132|9120|lpd_|net_pedk|net_proxy|network init|port913" | tail -30; sleep 120; echo "--- FINAL ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- FINAL LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; echo "--- FINAL UNIX ---"; cat /proc/net/unix 2>&1 | wc -l; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
print("tail -8 left:", "tail -8" in s)
