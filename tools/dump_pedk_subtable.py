# -*- coding: utf-8 -*-
"""dump mfp.afx rodata table at 0x821278 (6 x 16B) - PEDK sub-cmd table"""
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
print("rodata:", hex(by.get(".rodata", (0,0,0,0,0,0,0,0,0,0))[3]) if ".rodata" in by else "none")

def vaddr_to_off(va):
    for nm, s in by.items():
        if s[3] <= va < s[3] + s[5]:
            return s[4] + (va - s[3]), nm
    return None, None

for base in (0x821000, 0x821278, 0x821260):
    off, nm = vaddr_to_off(base)
    if off is None:
        print("va %#x: not in a section" % base)
        continue
    print("va %#x in %s off %#x" % (base, nm, off))
    blob = data[off:off+0x60]
    for i in range(0, 0x60, 16):
        cmd = struct.unpack_from("<I", blob, i)[0]
        pad = struct.unpack_from("<I", blob, i+4)[0]
        h = struct.unpack_from("<Q", blob, i+8)[0]
        print("  [%d] cmd=%#x pad=%#x handler=%#x" % (i//16, cmd, pad, h))
