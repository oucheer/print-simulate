# -*- coding: utf-8 -*-
"""round 74: dump .rodata 中 0x74f6dc 相关字符串（确认 LPD 服务启动日志与线程名），
并解析 .bss 段布局验证 0x15cf000e58 归属"""
import struct

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

print("=== sections (addr->name size) ===")
for i in range(e_shnum):
    nm = sec_name(i)
    if nm in (".text", ".rodata", ".data", ".bss", ".plt"):
        s = secs[i]
        print("  %-8s addr=0x%x size=0x%x" % (nm, s[3], s[5]))

def read_cstr(vaddr):
    # 找包含该 vaddr 的段
    for i in range(e_shnum):
        s = secs[i]
        if s[3] <= vaddr < s[3] + s[5]:
            off = s[4] + (vaddr - s[3])
            e = data.index(b"\0", off)
            return data[off:e].decode("utf-8", "replace")
    return None

print("\n=== strings around 0x85c000 (0x74f6dc 日志区) ===")
for delta in (0x2f0, 0x300, 0x340, 0x350, 0x390, 0x3b0, 0x3d0, 0x3f8, 0x5d0, 0x5e8):
    v = 0x85c000 + delta
    t = read_cstr(v)
    print("  0x%x: %r" % (v, t))

print("\n=== strings at 0x8a50cb0 (main/各线程栈保护) ===")
t = read_cstr(0x8a5000 + 0xcb0)
print("  0x8a50cb0: %r" % t)

print("\n=== 0x74c604 监听的提示字符串 0x85a000 区 ===")
for delta in (0xf10, 0xf20, 0xf30, 0xf40, 0xf50, 0xf60, 0xf70, 0xf80):
    v = 0x85a000 + delta
    t = read_cstr(v)
    print("  0x%x: %r" % (v, t))
