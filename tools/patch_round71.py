# -*- coding: utf-8 -*-
"""round 71: mfp 启动前 ulimit -n 4096 + 检查 0x24188 线程管理器 + 监听"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

# 1) mfp 启动前提升 fd 限制
old_launch = "export LD_PRELOAD=/lib/libbinder_stub.so; /usr/bin/mfp.afx > /tmp/mfp.log 2>&1 & MFP=$!"
new_launch = "export LD_PRELOAD=/lib/libbinder_stub.so; ulimit -n 4096 2>/dev/null; /usr/bin/mfp.afx > /tmp/mfp.log 2>&1 & MFP=$!"
assert old_launch in s, "launch anchor not found"
s = s.replace(old_launch, new_launch, 1)

# 2) 检查段替换
start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)
new_block = r'''2>&1 | tail -6; sleep 45; echo "--- ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- FD COUNT ---"; ls /proc/$MFP/fd 2>&1 | wc -l; echo "--- ULIMIT ---"; ulimit -n; echo "--- THREAD MGR ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "p/x pi_thread_prolog" -ex "p/x *(long*)((char*)pi_thread_prolog-0xd5d0+0x24188)" -ex "detach" 2>&1 | tail -4; echo "--- LISTEN 1 ---"; cat /proc/net/tcp 2>&1 | head -20; sleep 30; echo "--- LISTEN 2 ---"; cat /proc/net/tcp 2>&1 | head -20; echo "--- ALIVE 2 ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
print("ulimit added:", "ulimit -n 4096" in s)
