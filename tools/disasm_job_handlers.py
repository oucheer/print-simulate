# -*- coding: utf-8 -*-
"""disasm job_pedkapi 子表 handler 头部 + 引用字符串"""
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
ro = by.get(".rodata", None)
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

HANDLERS = {
    0x514: 0x6b6adc,
    0x516: 0x6b6b64,
    0x518: 0x6b7060,
    0x519: 0x6b740c,
    0x51a: 0x6b7500,
    0x51c: 0x6b7158,
}

def rd_str(addr):
    if ro is None:
        return ""
    if not (ro[3] <= addr < ro[3] + ro[5]):
        return ""
    off = addr - ro[3]
    e = data.index(b"\0", ro[4] + off)
    s = data[ro[4] + off:e].decode(errors="replace")
    return s if len(s) < 80 else s[:80]

def disasm_head(addr, size=0x60, label=""):
    off = text[4] + (addr - text[3])
    code = data[off:off + size]
    print(f"\n==== {label} @ 0x{addr:x} ====")
    for ins in md.disasm(code, addr):
        s = ""
        if ins.mnemonic == "adrp":
            try:
                base = int(ins.op_str.split("#0x")[1], 16)
            except Exception:
                base = 0
            s = f"  ; rodata base 0x{base:x}"
        print(f"  0x{ins.address:x}: {ins.mnemonic:<9} {ins.op_str}{s}")

for sub, h in HANDLERS.items():
    disasm_head(h, 0x50, f"sub_{sub:#x}")
