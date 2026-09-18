# -*- coding: utf-8 -*-
"""定位 _wait_for_peer：搜 'wait failed' 字符串引用点"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
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

# 1) 在 .rodata/.data 找 "wait failed" 字符串
for sname in (".rodata", ".data"):
    sec = by.get(sname)
    if not sec:
        continue
    blob = data[sec[4]:sec[4] + sec[5]]
    idx = blob.find(b"wait failed")
    if idx >= 0:
        addr = sec[3] + idx
        print(f"'{sname}' 'wait failed' @ 0x{addr:x}")

# 2) 扫描 .text 找 adrp+add 引用该字符串地址的指令
text = by[".text"]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
code = data[text[4]:text[4] + text[5]]
insns = list(md.disasm(code, text[3]))

# 收集所有 adrp 对（adrp x,page; add/add x, x, #off）引用点
target_addrs = [0]  # 用于收集
refs = []  # (insn_addr, target_addr)
i = 0
while i < len(insns):
    ins = insns[i]
    if ins.mnemonic == "adrp":
        # 解析 adrp：page 地址
        try:
            # op_str like "x0, #0x850000"
            reg = ins.op_str.split(",")[0].strip()
            page = int(ins.op_str.split("#")[1], 0)
        except Exception:
            i += 1
            continue
        # 看后续最多 4 条是否有 add/adds 使用同一 reg + imm
        for j in range(i + 1, min(len(insns), i + 5)):
            nxt = insns[j]
            if nxt.mnemonic in ("add", "adds") and nxt.op_str.startswith(reg + ", " + reg + ", #"):
                try:
                    off = int(nxt.op_str.split("#")[1], 0)
                except Exception:
                    break
                target = page + off
                if 0x800000 <= target <= 0x900000:  # .rodata 范围
                    refs.append((nxt.address, target))
                break
            if nxt.mnemonic != "nop":
                break
        i = j + 1 if "j" in dir() else i + 1
        if "j" in dir():
            del j
    else:
        i += 1

print(f"\ntotal rodata refs: {len(refs)}")
# 找引用 'wait failed' 及邻近字符串的
# 打印 'wait failed' 附近的字符串
rodata = by[".rodata"]
blob = data[rodata[4]:rodata[4] + rodata[5]]
idx = blob.find(b"wait failed")
# 打印字符串前后上下文
for delta in (-80, -40, 0, 40):
    p = idx + delta
    if p < 0:
        continue
    s = blob[max(0, p - 24):p + 60]
    # 提取可打印
    s2 = "".join(chr(c) if 32 <= c < 127 else "." for c in s)
    print(f"  ctx@{p}: {s2}")
