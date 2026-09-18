# -*- coding: utf-8 -*-
"""disasm mfp.afx 0x6b7570 (cmd 0x0d callback) + find s_reg_list writer (0x910e20 refs)"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

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
text = by[".text"]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

def disasm(addr, size, label=""):
    off = text[4] + (addr - text[3])
    code = data[off:off + size]
    print(f"\n==== {label} @ 0x{addr:x} ====")
    for ins in md.disasm(code, addr):
        print(f"  0x{ins.address:x}: {ins.mnemonic:<9} {ins.op_str}")

disasm(0x6b7570, 0x6b7800 - 0x6b7570, "callback_cmd0d_6b7570")

tdata = data[text[4]:text[4] + text[5]]
insns = list(md.disasm(tdata, text[3]))
refs = []
for i, ins in enumerate(insns):
    if ins.mnemonic == "adrp" and "#0x910000" in ins.op_str:
        for j in range(i, min(i+3, len(insns))):
            if insns[j].mnemonic == "add" and "#0xe20" in insns[j].op_str:
                refs.append(insns[j].address)
                break
print("\nrefs to 0x910e20:", ["%#x" % r for r in refs[:20]])
