# -*- coding: utf-8 -*-
"""高效版：扫 .text 中 adrp+add 引用目标地址"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
TARGETS = {0x74c604: "lpd_listen_svc", 0x74f6dc: "lpd_svc_starter", 0x15cf0e58: "g_lpd_thread_handle"}
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
insns = list(md.disasm(data[text[4]:text[4] + text[5]], text[3]))

# 单遍：记录 adrp(reg,page) 后立即在后续检查 add
pending = {}  # reg -> page
hits = []
for ins in insns:
    if ins.mnemonic == "adrp":
        try:
            reg = ins.op_str.split(",")[0].strip()
            page = int(ins.op_str.split("#")[1], 0)
            pending[reg] = (ins.address, page)
        except Exception:
            pass
    elif ins.mnemonic in ("add", "adds"):
        parts = ins.op_str.split(",")
        if len(parts) >= 3:
            dreg = parts[0].strip()
            sreg = parts[1].strip()
            if sreg in pending:
                try:
                    off = int(parts[2].split("#")[1], 0)
                except Exception:
                    continue
                adr, page = pending[sreg]
                val = page + off
                if val in TARGETS:
                    hits.append((ins.address, TARGETS[val]))
                del pending[sreg]
    elif ins.mnemonic == "bl":
        # 清空（避免跨函数误配）
        pending = {}

for addr, name in sorted(hits):
    print(f"  0x{addr:x}  ref {name}")

print(f"\ntotal: {len(hits)}")
