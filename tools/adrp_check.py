# -*- coding: utf-8 -*-
"""round 78: 精确计算 adrp 目标地址（页数 vs 字节偏移两种假设）"""
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
bss = by[".bss"]
print(".bss addr=0x%x end=0x%x" % (bss[3], bss[3] + bss[5]))

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True
off = text[4] + (0x74f6dc - text[3])
for ins in md.disasm(data[off:off + 0x60], 0x74f6dc):
    if ins.mnemonic == "adrp":
        imm = ins.operands[1].imm
        pc_page = ins.address & ~0xFFF
        tgt_pages = pc_page + (imm << 12)     # imm 按页数
        tgt_bytes = pc_page + imm              # imm 按字节偏移
        print("  0x%x adrp x%d imm=0x%x  [as-pages]=0x%x  [as-bytes]=0x%x" % (
            ins.address, ins.operands[0].reg - 1, imm, tgt_pages, tgt_bytes))
