# -*- coding: utf-8 -*-
"""libcommon.so: dump rodata around 0x578, find code refs to 'cmd register ok' string"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\lib\libcommon.so"
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
rodata = by[".rodata"]
text = by[".text"]
rd = data[rodata[4]:rodata[4] + rodata[5]]

# find 0x578 in rodata (LE)
pat = struct.pack("<I", 0x578)
hits = []
s = 0
while True:
    p = rd.find(pat, s)
    if p < 0:
        break
    hits.append(rodata[3] + p)
    s = p + 1
print("0x578 in .rodata:", ["%#x" % h for h in hits])
for h in hits[:3]:
    off = h - rodata[3]
    blob = rd[off-16:off+48]
    print("  dump @%#x: %s" % (h, blob.hex()))
    # interpret as cmd table entries (each entry maybe 8/16 bytes)
    print("  as BE32:", " ".join(hex(int.from_bytes(rd[off+i:off+i+4], 'big')) for i in range(0, 48, 4)))

# find code refs to string 0x348b0 via adrp+add
sv = 0x348b0
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
tdata = data[text[4]:text[4] + text[5]]
refs = []
for ins in md.disasm(tdata, text[3]):
    if ins.mnemonic == "adrp":
        # adrp xd, imm -> page
        try:
            dst = int(ins.op_str.split(",")[1].strip().rstrip("#"), 16) if "#" in ins.op_str else 0
        except Exception:
            dst = 0
        # approximate: adrp gives page base
        page = dst
        nxt = ins.address + 4
        if page <= sv < page + 0x1000:
            refs.append(ins.address)
print("adrp refs to page of 0x348b0:", ["%#x" % r for r in refs[:10]])

# also search rodata for cmd table: look for 0x578 followed by plausible fields
print("rodata size %#x" % len(rd))
