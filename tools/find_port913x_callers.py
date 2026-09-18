# -*- coding: utf-8 -*-
"""round 79: 找 port913x 相关函数的调用方 (bl)"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
TARGETS = {
    0x66b000: "bind_listen_66b0",
    0x67ad14: "port9120_handler_67ad14",
    0x67b014: "port9130_handler_67b014",
    0x67b314: "port9132_handler_67b314",
    0x67a948: "port9120_svc_67a948",
    0x67aa8c: "port9130_svc_67aa8c",
    0x67abd0: "port9132_svc_67abd0",
    0x67bc2c: "port913x_handler_thread",
    0x67c714: "port913x_prolog",
    0x6765f8: "reg_handler_6765f8",
}
data = open(PATH, "rb").read()
endian = "<"
e_shoff = struct.unpack_from(endian + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + "H", data, 0x3E)[0]
def gs(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(endian + "IIQQQQIIQQ", data, off)
secs = [gs(i) for i in range(e_shnum)]
shs = secs[e_shstrndx]; shd = data[shs[4]:shs[4] + shs[5]]
def sn(i):
    n = secs[i][0]; e = shd.index(b"\0", n); return shd[n:e].decode()
by = {sn(i): secs[i] for i in range(e_shnum)}
text = by[".text"]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

# bl 目标统计（全 .text）
calls = {}
insns = list(md.disasm(data[text[4]:text[4] + text[5]], text[3]))
for ins in insns:
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str.replace("#", ""), 0)
        except Exception:
            continue
        calls.setdefault(tgt, []).append(ins.address)

for tgt, name in sorted(TARGETS.items()):
    sites = calls.get(tgt, [])
    print("%-32s @ 0x%x called by %d site(s): %s" % (
        name, tgt, len(sites),
        ", ".join("0x%x" % a for a in sites[:12])))
