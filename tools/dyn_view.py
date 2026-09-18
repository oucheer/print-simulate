# -*- coding: utf-8 -*-
"""Step 4: mfp.afx 动态链接视图。
1) NEEDED 依赖库
2) .dynsym 导出符号（引擎相关）
3) .rela.dyn/.rela.plt 中引擎符号的重定位（GOT 偏移）
"""
import struct, sys
sys.stdout = open(r"runtime/dyn_view.txt", "w", encoding="utf-8", errors="replace")

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

# 1) NEEDED
print("== 1) 依赖库 (DT_NEEDED) ==")
strtab_va = None
dynsec = by.get(".dynamic")
if dynsec:
    dobj = data[dynsec[4]:dynsec[4] + dynsec[5]]
    for j in range(0, len(dobj) - 16, 16):
        tag = struct.unpack_from(endian + "q", dobj, j)[0]
        val = struct.unpack_from(endian + "Q", dobj, j + 8)[0]
        if tag == 5:
            strtab_va = val
            break
if strtab_va is not None:
    def dstr(off):
        p = v2o(strtab_va + off)
        if p is None:
            return "?"
        e = data.index(b"\0", p)
        return data[p:e].decode(errors="replace")
    for j in range(0, len(dobj) - 16, 16):
        tag = struct.unpack_from(endian + "q", dobj, j)[0]
        val = struct.unpack_from(endian + "Q", dobj, j + 8)[0]
        if tag == 1:
            print("  NEEDED: %s" % dstr(val))

# 2) .dynsym 引擎相关导出
print("\n== 2) .dynsym 引擎相关导出 ==")
if ".dynsym" in by and ".dynstr" in by:
    ds, dstrs = by[".dynsym"], by[".dynstr"]
    n = ds[5] // 24
    for k in range(n):
        e = struct.unpack_from(endian + "IBBHQQ", data, ds[4] + k * 24)
        name_off = e[0]; shndx = e[3]; value = e[4]; typ = e[1] & 0xf
        if typ in (1, 2) and shndx != 0:
            p = dstrs[4] + name_off
            end = data.index(b"\0", p)
            nm = data[p:end].decode(errors="replace")
            low = nm.lower()
            if "eng" in low or "if_layer" in low or "mmp" in low or "print" in low:
                print("  0x%x  %s (t=%d)" % (value, nm, typ))

# 3) 引擎符号的动态重定位
print("\n== 3) 引擎符号动态重定位 ==")
if ".dynsym" in by and ".dynstr" in by:
    ds, dstrs = by[".dynsym"], by[".dynstr"]
    for secname in (".rela.dyn", ".rela.plt"):
        if secname not in by:
            continue
        rs = by[secname]
        blk = data[rs[4]:rs[4] + rs[5]]
        for j in range(0, len(blk), 24):
            r_off, r_info, r_add = struct.unpack_from(endian + "QQq", blk, j)
            sym = r_info >> 32
            typ = r_info & 0xffffffff
            e = struct.unpack_from(endian + "IBBHQQ", data, ds[4] + sym * 24)
            p = dstrs[4] + e[0]
            end = data.index(b"\0", p)
            nm = data[p:end].decode(errors="replace")
            low = nm.lower()
            if "eng" in low or "if_layer" in low or "print" in low:
                print("  %s r_off=0x%x type=%d sym=%s" % (secname, r_off, typ, nm))