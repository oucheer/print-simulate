# -*- coding: utf-8 -*-
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()
old = r'''echo "--- INJECT TEST (module 0xe) ---"; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x05\x78\x00\x00\x00\x00\x00\x00\x00\x00' | nc 127.0.0.1 14279 > /tmp/nc1.log 2>&1 & sleep 2; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x03\xe8\x00\x00\x00\x00\x00\x00\x00\x00' | nc 127.0.0.1 14279 > /tmp/nc2.log 2>&1 & sleep 4;'''
new = r'''echo "--- INJECT TEST (busybox nc) ---"; ls -la /bin/nc /usr/bin/nc /bin/busybox 2>&1; busybox --list 2>/dev/null | grep -E "^(nc|telnet)$"; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x05\x78\x00\x00\x00\x00\x00\x00\x00\x00' | busybox nc 127.0.0.1 14279 > /tmp/nc1.log 2>&1 & sleep 2; printf '\x0a\x00\x11\x00\x00\x00\x00\x0e\x00\x00\x03\xe8\x00\x00\x00\x00\x00\x00\x00\x00' | busybox nc 127.0.0.1 14279 > /tmp/nc2.log 2>&1 & sleep 4;'''
assert old in s, "old inject not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")