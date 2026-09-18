# -*- coding: utf-8 -*-
"""round 63: 精简验证版 —— patch 后抓全线程 backtrace + socket 类型 + 长等待监听确认"""
import io

p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

# 1) 删除 PATCH_MARKER 占位（先前 Edit 引入的 gdb 无效命令）
s = s.replace(
    '-ex "PATCH_MARKER" -ex "p/x *(unsigned char*)(0xa91370+0x5c)"',
    '-ex "p/x *(unsigned char*)(0xa91370+0x5c)"',
)

# 2) 替换检查段（从 tail -30 到 echo done）
start_marker = "2>&1 | tail -30; sleep 15;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)
new_block = (
    '2>&1 | tail -8; sleep 20; '
    'echo "--- CHECK ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; '
    'echo "--- NET GLOBALS ---"; dd if=/proc/$MFP/mem bs=1 count=4 skip=$((0xa921c8)) 2>/dev/null | od -An -tx4; '
    'echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; '
    'echo "--- UNIX SOCK COUNT ---"; cat /proc/net/unix 2>&1 | wc -l; '
    'echo "--- SOCK FDS ---"; ls -l /proc/$MFP/fd 2>&1 | grep socket | head -25; '
    'echo "--- BT DUMP ---"; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 4" -ex "detach" > /tmp/bt.txt 2>&1; '
    'echo "BT_LINES=$(wc -l < /tmp/bt.txt)"; '
    'grep -aiE "lpd|port913|net_proxy|netdata|listen|bind|print_info_status" /tmp/bt.txt | head -30; '
    'echo "--- MFP LOG NET ---"; tail -c 50000 /tmp/mfp.log 2>&1 | grep -aiE "listen|bind|port|9130|9132|9120|lpd|net_pedk|net_proxy|network" | tail -20; '
    'sleep 60; '
    'echo "--- FINAL ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; '
    'echo "--- FINAL LISTEN ---"; cat /proc/net/tcp 2>&1 | head -20; '
    "echo done'"
)
s = s[:i] + new_block + s[j:]

open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK, new length:", len(s))
print("PATCH_MARKER left:", "PATCH_MARKER" in s)
print("tail -30 left:", "tail -30" in s)
