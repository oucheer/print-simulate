# -*- coding: utf-8 -*-
"""Step 5 s5b: 反汇编 libhal.so 的 pi_hal_gpio_* 推断参数签名。
输出到 runtime/libhal_gpio_disasm.txt
"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime/unpacked/rkaf/rootfs/usr/lib/libhal.so"
OUT = r"runtime/libhal_gpio_disasm.txt"
TARGETS = {
    "pi_hal_gpio_request": 0x16630,
    "pi_hal_gpio_free": 0x16910,
    "pi_hal_gpio_getinfo": 0x16b28,
    "pi_hal_gpio_set": 0x16cf8,
    "pi_hal_gpio_get": 0x16ec8,
    "pi_hal_power_set": 0x179c0,
    "pi_hal_power_get": 0x17b90,
    "pi_hal_led_ctrl": 0x16200,
}

data = open(PATH, "rb").read()
endian = "<" if data[5] == 1 else ">"
# 解析 section headers 得到 addr->offset 映射
e_shoff = struct.unpack_from(endian + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + "H", data, 0x3E)[0]

def gs(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(endian + "IIQQQQIIQQ", data, off)

secs = [gs(i) for i in range(e_shnum)]
shs = secs[e_shstrndx]
shd = data[shs[4]:shs[4] + shs[5]]
def sn(i):
    n = secs[i][0]
    e = shd.index(b"\0", n)
    return shd[n:e].decode()

def v2o(v):
    for s in secs:
        if s[3] <= v < s[3] + s[5] and s[4]:
            return s[4] + (v - s[3])
    return None

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True

out_lines = []
def p(*a):
    out_lines.append(" ".join(str(x) for x in a))

for name, addr in TARGETS.items():
    p("=" * 60)
    p("== %s @ 0x%x ==" % (name, addr))
    off = v2o(addr)
    if off is None:
        p("  [无法定位文件偏移]")
        continue
    # 反汇编约 80 条指令（多数函数 < 0x400 字节）
    code = data[off:off + 0x400]
    end_addr = addr + len(code)
    # 记录 bl 调用目标（通过 PLT 或直接），以及 adrp/ldr 全局引用
    for ins in md.disasm(code, addr):
        line = "  0x%x: %s %s" % (ins.address, ins.mnemonic, ins.op_str)
        p(line)
    p("")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))
print("done ->", OUT, "lines:", len(out_lines))
