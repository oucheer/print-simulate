# -*- coding: utf-8 -*-
"""round 78: 手动解码 adrp 指令得到确切目标页地址"""
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
for nm in (".text", ".rodata", ".data", ".bss"):
    s = by[nm]
    print("  %-7s addr=0x%-9x end=0x%x" % (nm, s[3], s[3] + s[5]))

def decode_adrp(vaddr):
    off = text[4] + (vaddr - text[3])
    raw = struct.unpack_from("<I", data, off)[0]
    immhi = (raw >> 5) & 0x7FFFF
    immlo = (raw >> 29) & 0x3
    imm = (immhi << 2) | immlo
    # 21 位符号扩展
    if imm & (1 << 20):
        imm -= (1 << 21)
    page = (vaddr & ~0xFFF) + (imm << 12)
    return page

print("\n=== adrp decode in 0x74f6dc ===")
for va in (0x74f6f0, 0x74f708, 0x74f718, 0x74f724, 0x74f77c, 0x74f7c0):
    page = decode_adrp(va)
    print("  0x%x adrp -> page 0x%x" % (va, page))

# 常用全局：s_semaphore_pool 等确认方法一致
print("\n=== 其他已知 adrp 验证 ===")
for va, add in ((0x74c614, 0xcb0), (0x74c66c, 0xf20)):
    page = decode_adrp(va)
    print("  0x%x adrp -> page 0x%x + 0x%x = 0x%x" % (va, page, add, page + add))
