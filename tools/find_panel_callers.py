# -*- coding: utf-8 -*-
"""找 0x73b30c / 0x73b71c 的调用者（bl 引用）+ dump 0x6b7570 分发逻辑片段"""
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

# 找 .text 中 bl 0x73b30c / bl 0x73b71c 的调用者
tdata = data[text[4]:text[4] + text[5]]
insns = list(md.disasm(tdata, text[3]))
TARGETS = {0x73b30c: "panel_line16", 0x73b71c: "panel_line118", 0x734e70: "log734e70", 0x6b7570: "job_pedk_disp"}
callers = {t: [] for t in TARGETS}
for i, ins in enumerate(insns):
    if ins.mnemonic == "bl":
        for t, name in TARGETS.items():
            if ins.op_str.endswith("#0x%x" % t):
                callers[t].append(ins.address)
                break
for t, name in TARGETS.items():
    print(f"callers of {name} (0x{t:x}):", ["%#x" % c for c in callers[t][:30]])
