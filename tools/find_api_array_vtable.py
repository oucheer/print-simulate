# -*- coding: utf-8 -*-
"""Step 4: 定位 get_api_array(0x4e84fc) 被放入的函数指针表 + api_array(0x8b06f0) 符号名。
1) 所有数据段 8B 指针 == 0x4e84fc（getter 的 vtable 宿主）
2) .symtab 中 0x8b06f0 / 0x4e84fc 符号名
3) 若宿主表存在，转储整表并解析每项符号
"""
import struct, sys
sys.stdout = open(r"runtime/api_array_vtable.txt", "w", encoding="utf-8", errors="replace")

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

# 1) 找 getter 被放入的表
GETTER = 0x4e84fc
print("== 1) 数据段 8B 指针 == 0x4e84fc (get_api_array) ==")
hosts = []
for n, s in by.items():
    if not s[4] or n in (".text", ".bss"):
        continue
    blk = data[s[4]:s[4] + s[5]]
    i = 0
    while True:
        i = blk.find(struct.pack("<Q", GETTER), i)
        if i < 0:
            break
        hosts.append((n, s[3] + i))
        print("  %s @ 0x%x -> get_api_array" % (n, s[3] + i))
        i += 1
print("  共 %d 处" % len(hosts))

# 2) symtab 符号名
print("\n== 2) symtab 符号名 ==")
SYMTAB_OFF = None
for n, s in by.items():
    if n == ".symtab":
        SYMTAB_OFF = s[4]; LINK = s[5]; continue
if SYMTAB_OFF is not None:
    # sh_link = 字符串表段索引；从 secs 推断 .strtab
    strtab = None
    for n, s in by.items():
        if n == ".strtab":
            strtab = s; break
    if strtab:
        entsize = 24
        for i in range(0, LINK // entsize):
            e = struct.unpack_from(endian + "IBBHQQ", data, SYMTAB_OFF + i * entsize)
            name_off, info, other, shndx, value, size = e
            if value in (0x8b06f0, GETTER, 0x4e84fc):
                # 解出名字
                st = strtab[4]
                nm = data[strtab[4] + name_off:data.index(b"\0", strtab[4] + name_off)].decode(errors="replace")
                print("  0x%x : %s (type=%d)" % (value, nm, info & 0xf))

# 3) 若找到宿主表，转储整表并解析符号
print("\n== 3) 宿主表转储 ==")
for n, h in hosts:
    s = by[n]
    base = h - (h % 8)
    print("\n--- %s @ 0x%x 周围 0x80 字节 (%d 项) ---" % (n, base, 0x80 // 8))
    off = v2o(base)
    if off is None:
        continue
    for k in range(0x80 // 8):
        v = struct.unpack_from("<Q", data, off + k * 8)[0]
        tag = ""
        # 尝试匹配函数指针到已知符号（用 symtab 构建 addr->name）
        print("  [%2d] 0x%x : 0x%x %s" % (k, base + k * 8, v, tag))
