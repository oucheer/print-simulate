# -*- coding: utf-8 -*-
"""Step 4: 定位 s_engframework_api_array (0x8b06f0) 的分发调用者。
扫描 .text 中 adrp #0x8b0000 + add #0x6f0 (0x8b06f0) / 直接 ldr 该地址的模式，
反汇编命中点周围代码，找出按 API ID 查表分发的函数。
"""
import struct, sys
sys.stdout = open(r"runtime/api_array_callers.txt", "w", encoding="utf-8", errors="replace")
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
data = open(PATH, "rb").read()
endian = "<" if data[5] == 1 else ">"
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
def v2o(v):
    for s in secs:
        if s[3] <= v < s[3] + s[5] and s[4]:
            return s[4] + (v - s[3])
    return None

TARGET = 0x8b06f0   # s_engframework_api_array
ADRP_PG = TARGET & ~0xFFF          # 0x8b0000
ADD_OFF = TARGET & 0xFFF           # 0x6f0

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
text = by[".text"]
tblk = data[text[4]:text[4] + text[5]]

# 收集所有 adrp #0x8b0000 的位置，检查后续 add #0x6f0 或 ldr/ldrsw 引用
hits = []
insns = list(md.disasm(tblk, text[3]))
for i, ins in enumerate(insns):
    if ins.mnemonic != "adrp":
        continue
    try:
        pg = int(ins.op_str.split("#")[1], 0)
    except Exception:
        continue
    if pg != ADRP_PG:
        continue
    # 向后最多看 6 条，找 add xN, xN, #0x6f0 / #0x6f8 / #0x6e0 等指向 0x8b06f0 附近
    for j in range(i + 1, min(i + 7, len(insns))):
        n = insns[j]
        if n.mnemonic == "add" and "#" in n.op_str:
            try:
                base, offs = n.op_str.split(", ")[1], n.op_str.split("#")[1]
                off = int(offs, 0)
            except Exception:
                continue
            if off >= 0x6e0 and off <= 0x710:
                hits.append((ins.address, n.address, off))
                break
        if n.mnemonic == "ldr" and "#" in n.op_str:
            # 形式: ldr xN, [xM, #0x6f0]
            try:
                br = n.op_str.split("[")[1].split("]")[0]
                offs = br.split("#")[1]
                off = int(offs, 0)
            except Exception:
                continue
            if off >= 0x6e0 and off <= 0x710:
                hits.append((ins.address, n.address, off))
                break

print("== adrp #0x%x + add/ldr 指向 0x8b06f0 附近的命中: %d ==" % (ADRP_PG, len(hits)))
for a, b, off in hits:
    print("  adrp @0x%x -> add/ldr @0x%x (off=0x%x)" % (a, b, off))

# 对每个命中，反汇编 adrp 前 8 条到后 24 条，识别分发函数
print("\n\n== 分发函数反汇编 ==")
seen = set()
for a, b, off in hits:
    start = a - 0x20
    size = (b + 8) - start + 0x40
    so = v2o(start)
    if so is None:
        continue
    func = None
    # 向前回退到函数入口 stp x29,x30 (常见 prologue)
    for k in range(so, so - 0x200, -4):
        pass
    # 简单方式: 打印 adrp 之前 0x40 字节开始的代码
    print("\n--- 命中链 0x%x -> 0x%x ---" % (a, b))
    for ins in md.disasm(data[so:so + size], start):
        mark = " <== TARGET" if ins.address in (a, b) else ""
        print("  0x%x: %-8s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
