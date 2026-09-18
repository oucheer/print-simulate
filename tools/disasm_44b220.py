# -*- coding: utf-8 -*-
"""disasm 0x44b220（事件发布函数头部）+ 0x734e2c（事件处理回调）"""
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

disasm(0x44b220, 0x44b400 - 0x44b220, "event_publish_44b220")
disasm(0x734e2c, 0x734e70 - 0x734e2c, "event_cb_734e2c")
