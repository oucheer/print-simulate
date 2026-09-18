# -*- coding: utf-8 -*-
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()
marker = 'echo "KEEPING MFP ALIVE (pid $MFP)"'
inject = r"""echo "--- INJECT TEST (module 0xe) ---"; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x05\x78\x00\x00\x00\x00\x00\x00\x00\x00' | nc 127.0.0.1 14279 > /tmp/nc1.log 2>&1 & sleep 2; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x03\xe8\x00\x00\x00\x00\x00\x00\x00\x00' | nc 127.0.0.1 14279 > /tmp/nc2.log 2>&1 & sleep 4; echo "--- MFP LOG AFTER INJECT ---"; grep -aE "==>|recvStruct|pedk_mgr|module|578" /tmp/mfp.log | tail -25; echo "--- NC LOGS ---"; cat /tmp/nc1.log 2>&1 | head -3; cat /tmp/nc2.log 2>&1 | head -3; """
assert marker in s, "marker not found"
s = s.replace(marker, inject + marker)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")