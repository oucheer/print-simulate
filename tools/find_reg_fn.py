# -*- coding: utf-8 -*-
"""libcommon.so: find code ref to 'cmd register ok' rodata 0x348b0, disasm register fn; locate 0x578 const offset+section"""
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
text = by[".text"]

# 1) full-file location of LE32 0x578
pat = struct.pack("<I", 0x578)
pos = data.find(pat)
print("0x578 LE at file off=%#x" % pos)
for nm, s in by.items():
    if s[4] <= pos < s[4] + s[5]:
        print("  in section %s vaddr=%#x" % (nm, s[3] + (pos - s[4])))
        break

# 2) scan .text for adrp page 0x348000 + add 0x8b0 referencing string
target_page = 0x348000
target_off = 0x8b0
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
tdata = data[text[4]:text[4] + text[5]]
insns = list(md.disasm(tdata, text[3]))
adrp_pages = {}
for i, ins in enumerate(insns):
    if ins.mnemonic == "adrp" and "#" in ins.op_str:
        try:
            pg = int(ins.op_str.split("#")[1].strip(), 16)
        except Exception:
            pg = -1
        adrp_pages[i] = pg
# find add following adrp
for i in range(len(insns) - 1):
    ins = insns[i]
    if ins.mnemonic == "add" and "#" in ins.op_str and ", x0" in ins.op_str and ins.address > text[3]:
        try:
            imm = int(ins.op_str.split("#")[1].strip(), 16)
        except Exception:
            continue
        if imm == target_off:
            # find preceding adrp x0 with page target_page
            for j in range(max(0, i - 8), i):
                if j in adrp_pages and adrp_pages[j] == target_page:
                    print("REF adrp@%#x add@%#x" % (insns[j].address, ins.address))
