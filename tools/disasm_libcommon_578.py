# -*- coding: utf-8 -*-
"""locate 0x578 const in libcommon.so, disasm around it"""
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
print("sections:", {k: (hex(v[3]), hex(v[4]), hex(v[5])) for k, v in by.items() if k in ('.text', '.rodata', '.data', '.bss')})
text = by[".text"]
tdata = data[text[4]:text[4] + text[5]]

# find LE32 0x578 in .text
pat = struct.pack("<I", 0x578)
hits = []
s = 0
while True:
    p = tdata.find(pat, s)
    if p < 0:
        break
    hits.append(text[3] + p)
    s = p + 1
print("0x578 const hits:", ["%#x" % h for h in hits])

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
def disasm(addr, size, label=""):
    off = text[4] + (addr - text[3])
    code = data[off:off + size]
    print(f"\n==== {label} @ 0x{addr:x} ====")
    for ins in md.disasm(code, addr):
        print(f"  0x{ins.address:x}: {ins.mnemonic:<9} {ins.op_str}")

# also find string ref to 'cmd register ok' rodata vaddr
rodata = by[".rodata"]
spos = data.find(b"cmd register ok")
svaddr = rodata[3] + (spos - rodata[4]) if spos >= rodata[4] else None
print("'cmd register ok' rodata vaddr:", hex(svaddr) if svaddr else None)

for h in hits:
    disasm(h - 32, 160, "const_0x578_ref")
