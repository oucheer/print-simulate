# -*- coding: utf-8 -*-
"""round 77: strace 抓 bind errno（修正 round 76 问题）

round 76 失败：strace.log 不存在 = strace 启动失败。嫌疑：LD_PRELOAD binder_stub
对 strace 自身干扰。修正：strace 不带 preload，用 env 只给 mfp 注入 LD_PRELOAD；
加 strace --version 确认、ls strace.log、mfp.log 原文 head 以便诊断。
"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start = 'ip link set lo up 2>&1; export LD_PRELOAD'
end = 'echo done'
i = s.index(start)
j = s.index(end, i) + len(end)

new_block = r'''ip link set lo up 2>&1; ulimit -n 4096 2>/dev/null; echo "--- STRACE VER ---"; /usr/bin/strace --version 2>&1 | head -2; /usr/bin/strace -f -e trace=socket,bind,listen,accept,connect,getsockname -s 80 -o /tmp/strace.log /usr/bin/env LD_PRELOAD=/lib/libbinder_stub.so /usr/bin/mfp.afx > /tmp/mfp.log 2>&1 & MFP=$!; echo "MFP_PID=$MFP (strace parent)"; sleep 600; echo "--- STRACE FILE ---"; ls -la /tmp/strace.log 2>&1; echo "--- MFP LOG HEAD ---"; head -c 2500 /tmp/mfp.log 2>&1; echo; echo "--- PEDK/BIND ---"; grep -aE "pedk|bind|strat|server_thread" /tmp/mfp.log 2>&1 | tail -12; echo "--- KILL ---"; kill -9 $MFP 2>/dev/null; sleep 2; echo "--- BIND/SOCKET ---"; grep -aE "bind\(|socket\(|listen\(|accept|connect\(" /tmp/strace.log 2>&1 | head -40; echo "--- ERRNO ---"; grep -aE "= -1" /tmp/strace.log 2>&1 | head -20; echo done'''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
