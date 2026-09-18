# -*- coding: utf-8 -*-
"""search libcommon.so for cmd register strings and 0x578/0x3e8 constants"""
import struct, os

paths = [r"runtime\unpacked\rkaf\rootfs\usr\lib\libcommon.so",
         r"printer-sim-poc\poc-out\firmware\usr\lib\libcommon.so",
         r"runtime\unpacked\rkaf\rootfs\usr\lib\libevent_mgr.so",
         r"runtime\unpacked\rkaf\rootfs\usr\lib\libhal.so",
         r"runtime\unpacked\rkaf\rootfs\usr\lib\libosal.so"]

targets = [b"cmd register ok", b"panel - pedk", b"panel", b"pedk", b"cmd register", b"print job", b"0x578"]
for p in paths:
    if not os.path.exists(p):
        print("MISS", p)
        continue
    data = open(p, "rb").read()
    hits = {}
    for t in targets:
        offs = []
        s = 0
        while True:
            q = data.find(t, s)
            if q < 0:
                break
            offs.append(q)
            s = q + 1
        if offs:
            hits[t.decode(errors="ignore")] = offs[:3]
    print("=== %s (%d bytes)" % (p, len(data)))
    for k, v in hits.items():
        print("   %r @ %s" % (k, ["%#x" % o for o in v]))
    # text 0x578/0x3e8 LE search
    for val, nm in [(0x578, "0x578"), (0x3e8, "0x3e8"), (0x0e, "0x0e")]:
        pat = struct.pack("<I", val)
        n = data.count(pat)
        print("   LE32 %s: %d" % (nm, n))
