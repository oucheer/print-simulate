# -*- coding: utf-8 -*-
"""find cmd register value for panel-pedk"""
import struct

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
data = open(PATH, "rb").read()
endian = "<" if data[5] == 1 else ">"
e_shoff = struct.unpack_from(endian + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + "H", data, 0x3E)[0]

def get_sec(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(endian + "IIQQQQIIQQ", data, off)

secs = [get_sec(i) for i in range(e_shnum)]
shstr = secs[e_shstrndx]
shstr_data = data[shstr[4]:shstr[4] + shstr[5]]
def sec_name(i):
    n = secs[i][0]
    e = shstr_data.index(b"\0", n)
    return shstr_data[n:e].decode()
by = {sec_name(i): secs[i] for i in range(e_shnum)}
rodata = by.get(".rodata")
text = by[".text"]
print("rodata vaddr=%#x off=%#x size=%#x" % (rodata[3], rodata[4], rodata[5]))

targets = [b"cmd register ok", b"panel - pedk", b"pedk_mgr_prolog"]
for t in targets:
    offs = []
    s = 0
    while True:
        p = data.find(t, s)
        if p < 0:
            break
        offs.append(p)
        s = p + 1
    if offs and rodata[4] <= offs[0] < rodata[4] + rodata[5]:
        vaddr = rodata[3] + (offs[0] - rodata[4])
        print("str %r vaddr=%#x" % (t, vaddr))
    else:
        print("str %r offs=%s" % (t, ["%#x" % o for o in offs[:5]]))

tdata = data[text[4]:text[4] + text[5]]
for val, name in [(0x578, "0x578"), (0x3e8, "0x3e8")]:
    pat = struct.pack("<I", val)
    hits = []
    s = 0
    while True:
        p = tdata.find(pat, s)
        if p < 0:
            break
        hits.append(text[3] + p)
        s = p + 1
    print("LE32 %s: %d hits: %s" % (name, len(hits), ["%#x" % h for h in hits[:12]]))
