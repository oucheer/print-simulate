# -*- coding: utf-8 -*-
"""Step 5 s5a: dump 外部依赖库的导出符号（Virtual HAL 接口清单）。
用法: python dump_so_exports.py   # 输出到 runtime/so_exports.txt
"""
import struct, sys

OUT = r"runtime/so_exports.txt"
LIBS = [
    (r"runtime\unpacked\rkaf\rootfs\usr\lib\libhal.so", "libhal.so"),
    (r"runtime\unpacked\rkaf\rootfs\usr\lib\libipm.so", "libipm.so"),
    (r"runtime\unpacked\rkaf\rootfs\usr\lib\libparser_ips.so", "libparser_ips.so"),
]
if len(sys.argv) > 1 and sys.argv[1] == "--common":
    LIBS.append((r"runtime\unpacked\rkaf\rootfs\usr\lib\libcommon.so", "libcommon.so"))

def dump(path, name, outp):
    data = open(path, "rb").read()
    if data[:4] != b"\x7fELF":
        outp.write("== %s: NOT ELF ==\n\n" % name)
        return
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
    outp.write("== %s ==\n" % name)
    if ".dynsym" in by and ".dynstr" in by:
        ds, dstrs = by[".dynsym"], by[".dynstr"]
        n = ds[5] // 24
        funcs, objs, total = [], [], 0
        for k in range(n):
            e = struct.unpack_from(endian + "IBBHQQ", data, ds[4] + k * 24)
            name_off, bind, typ = e[0], e[1] >> 4, e[1] & 0xf
            value = e[4]
            if name_off == 0 or bind not in (1, 2):
                continue
            p = dstrs[4] + name_off
            end = data.index(b"\0", p)
            nm = data[p:end].decode(errors="replace")
            total += 1
            if typ == 2 and value:
                funcs.append("%s @ 0x%x" % (nm, value))
            elif typ == 1 and value:
                objs.append("%s @ 0x%x" % (nm, value))
        outp.write("  [导出总数 %d | FUNC %d | OBJ %d]\n" % (total, len(funcs), len(objs)))
        outp.write("  -- FUNC --\n")
        for f in sorted(funcs):
            outp.write("    %s\n" % f)
        if objs:
            outp.write("  -- OBJ/DATA --\n")
            for o in sorted(objs):
                outp.write("    %s\n" % o)
    if ".dynsym" in by:
        ds = by[".dynsym"]
        n = ds[5] // 24
        imported = []
        for k in range(n):
            e = struct.unpack_from(endian + "IBBHQQ", data, ds[4] + k * 24)
            name_off, shndx, typ = e[0], e[3], e[1] & 0xf
            if name_off == 0 or shndx != 0:
                continue
            p = by[".dynstr"][4] + name_off
            end = data.index(b"\0", p)
            imported.append(data[p:end].decode(errors="replace"))
        outp.write("  -- UND(imported) %d --\n" % len(imported))
        for nm in sorted(imported):
            outp.write("    %s\n" % nm)
    outp.write("\n")

with open(OUT, "w", encoding="utf-8", errors="replace") as out:
    for p, n in LIBS:
        dump(p, n, out)
print("done ->", OUT)