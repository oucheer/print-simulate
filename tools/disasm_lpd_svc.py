# -*- coding: utf-8 -*-
"""定位 LPD 监听 socket 的真实创建/accept 代码路径。

产出:
  1) 关键地址区间内的函数符号
  2) 0x74c604 附近完整反汇编（socket/bind/listen/accept 一体化点）
  3) 0x5fa168 / 0x5f9f78（lpd_listen_create 内的两次调用）
  4) 0x85a000+0xf10..0xf80 / 0x85c000 相关日志字符串
用法: python tools/disasm_lpd_svc.py [outfile]
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"

if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
    sys.stdout = open(sys.argv[1], "w", encoding="utf-8")

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
shs = secs[e_shstrndx]
shd = data[shs[4]:shs[4] + shs[5]]


def sn(i):
    n = secs[i][0]
    e = shd.index(b"\0", n)
    return shd[n:e].decode()


by = {sn(i): secs[i] for i in range(e_shnum)}
text = by[".text"]
symtab_name = ".dynsym" if ".dynsym" in by else ".symtab"
dsym = by[symtab_name]
dstr = by[".dynstr" if symtab_name == ".dynsym" else ".strtab"]

funcs = []  # (addr, size, name)
for off in range(0, dsym[5], 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
        endian + "IBBHQQ", data, dsym[4] + off)
    if st_name == 0 or st_value == 0:
        continue
    e = dstr[4] + st_name
    end = data.index(b"\0", e)
    name = data[e:end].decode(errors="replace")
    if name and (st_info & 0xF) == 2:
        funcs.append((st_value, st_size, name))
funcs.sort()

print("== ELF 类型 ==")
e_type = struct.unpack_from(endian + "H", data, 0x10)[0]
print("  e_type = %d (%s)" % (e_type, {0: "NONE", 1: "REL", 2: "EXEC", 3: "DYN/PIE"}.get(e_type, "?")))
print("  .text vaddr=0x%x size=0x%x fileoff=0x%x" % (text[3], text[5], text[4]))

RANGES = [
    (0x449e00, 0x44c200, "PLT 区"),
    (0x5f9e00, 0x5fa400, "lpd_listen_create 内被调"),
    (0x669900, 0x66c600, "通用 server 框架（socket/bind/listen/accept）"),
    (0x74c400, 0x74c800, "lpd_listen_svc 区"),
    (0x74f600, 0x74f800, "lpd_svc_starter 区"),
    (0x683400, 0x683f00, "lpd.c lpd_thread 区"),
]
for lo, hi, label in RANGES:
    print("\n== 符号 %s (0x%x..0x%x) ==" % (label, lo, hi))
    for a, sz, nm in funcs:
        if lo <= a < hi:
            print("  0x%-8x size=0x%-6x %s" % (a, sz, nm))


md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def symname(a):
    best = None
    for fa, sz, nm in funcs:
        if fa <= a < fa + max(sz, 4):
            best = nm
    return best or ("sub_%x" % a)


def disasm(addr, size, label=""):
    print("\n=== %s @ 0x%x (size=0x%x) ===" % (label or symname(addr), addr, size))
    fo = text[4] + (addr - text[3])
    for ins in md.disasm(data[fo:fo + size], addr):
        ann = ""
        if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("#"):
            try:
                tgt = int(ins.op_str.lstrip("#"), 0)
                ann = "  ; %s" % symname(tgt)
            except Exception:
                pass
        print("  0x%x: %-9s %s%s" % (ins.address, ins.mnemonic, ins.op_str, ann))


def read_cstr(vaddr):
    for i in range(e_shnum):
        s = secs[i]
        if s[3] and s[3] <= vaddr < s[3] + s[5]:
            off = s[4] + (vaddr - s[3])
            e = data.index(b"\0", off)
            return data[off:e].decode("utf-8", "replace")
    return None


print("\n== 日志字符串 ==")
for base, deltas in ((0x85a000, (0xf10, 0xf20, 0xf30, 0xf38, 0xf40, 0xf48, 0xf50, 0xf60, 0xf68, 0xf70)),
                     (0x85c000, (0x2f0, 0x300, 0x340, 0x350, 0x390, 0x3b0, 0x3d0))):
    for d in deltas:
        v = base + d
        print("  0x%x: %r" % (v, read_cstr(v)))

disasm(0x74c604, 0x1a0, "lpd_listen_svc 疑似")
disasm(0x5fa168, 0x180, "lpd_listen_create 调用1")
disasm(0x5f9f78, 0x180, "lpd_listen_create 调用2")
