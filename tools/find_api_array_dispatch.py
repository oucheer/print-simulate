# -*- coding: utf-8 -*-
"""Step 4: 追 engine_general_if_layer_get_api_array (0x4e84fc) 的调用者，
以及 api_array 真正被使用的分发函数（可能通过 Getter 返回指针再 ldr 索引）。
"""
import struct, sys
sys.stdout = open(r"runtime/api_array_dispatch.txt", "w", encoding="utf-8", errors="replace")
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

GETTER = 0x4e84fc   # engine_general_if_layer_get_api_array
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
text = by[".text"]
tblk = data[text[4]:text[4] + text[5]]

# 1) 找到所有 bl #0x4e84fc 调用点
print("== 1) bl 0x4e84fc (get_api_array) 调用点 ==")
calls = []
for i in range(0, len(tblk) - 4, 4):
    ins = next(md.disasm(tblk[i:i + 4], text[3] + i))
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str, 16)
        except Exception:
            continue
        if tgt == GETTER:
            calls.append(text[3] + i)
            print("  bl @ 0x%x" % (text[3] + i))

# 2) 若没有直接 bl，可能在 PLT/间接；也扫描 getter 函数体 0x4e84fc~0x4e8580 反汇编确认
print("\n== 2) getter 函数 0x4e84fc 反汇编 ==")
off = v2o(0x4e84fc)
if off is not None:
    for ins in md.disasm(data[off:off + 0x90], 0x4e84fc):
        print("  0x%x: %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))

# 3) 找所有指向 0x8b06f0 的引用（任意段，含 8B 指针），看是否有函数表拷贝
print("\n== 3) 全段 8B 指针指向 0x8b06f0 ==")
cnt = 0
for n, s in by.items():
    if not s[4] or n in (".text", ".bss"):
        continue
    blk = data[s[4]:s[4] + s[5]]
    i = 0
    while True:
        i = blk.find(struct.pack("<Q", 0x8b06f0), i)
        if i < 0:
            break
        print("  %s @ 0x%x -> 0x8b06f0" % (n, s[3] + i))
        cnt += 1
        i += 1
print("  共 %d 处" % cnt)
