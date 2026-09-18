# -*- coding: utf-8 -*-
"""round 75: 修正句柄地址(0x15cf000e58) + 修 FUNC DIST grep(双空格) + grep mfp.log 的 pedk/LPD 日志

背景：round 74 误读 0x15cf0e58(页未映射) 因 adrp 页数换算错误，正确地址 0x15cf000e58。
FUNC DIST 的 grep "^#0 " 匹配不到 gdb 的 "#0  "（双空格），导致统计恒为空。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start = 'echo "--- LPD HANDLES ---"; gdb'
end = 'echo done'
i = s.index(start)
j = s.index(end, i) + len(end)

new_block = r'''echo "--- LPD LOG ---"; grep -aE "pedk|IBC receive|server_thread|socket|bind|listen|accept|initialize failed" /tmp/mfp.log | tail -30; echo "--- LPD HANDLES(corrected) ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x *(long*)0x15cf000e58" -ex "p/x *(long*)0x15cf000e68" -ex "p/x *(long*)0x15cf000df0" -ex "detach" 2>&1 | tail -8; echo "--- FUNC DIST ---"; timeout 120 gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 1" -ex "detach" > /tmp/bt.txt 2>&1; echo "BT=$(wc -l < /tmp/bt.txt)"; grep "^#0" /tmp/bt.txt | sed "s/.*in //; s/ (.*//" | sort | uniq -c | sort -rn | head -30; echo "--- SERVER THREAD ---"; grep -E "0x74c[0-9a-f]{2}|0x74f[0-9a-f]{2}|0x74cd|server_thread|pedk_ibc" /tmp/bt.txt | head -25; echo "--- LISTEN ---"; cat /proc/net/tcp 2>&1 | head -25; echo done'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
