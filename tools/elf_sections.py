#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出 ELF 的 section 头（名称/类型/地址/偏移/大小），用于确认是否存在 DWARF 调试段。"""
import struct
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "mfp.afx"
data = open(path, "rb").read()

# ELF64 header
if data[:4] != b"\x7fELF":
    print("not ELF")
    sys.exit(1)
e_shoff, = struct.unpack_from("<Q", data, 0x28)
e_shentsize, = struct.unpack_from("<H", data, 0x3A)
e_shnum, = struct.unpack_from("<H", data, 0x3C)
e_shstrndx, = struct.unpack_from("<H", data, 0x3E)

secs = []
for i in range(e_shnum):
    o = e_shoff + i * e_shentsize
    name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from("<IIQQQQIIQQ", data, o)
    secs.append((name, typ, flags, addr, off, size, link, info, align, entsize))

shstr = secs[e_shstrndx]
strtab = data[shstr[4]:shstr[4] + shstr[5]]


def sn(i):
    n = secs[i][0]
    end = strtab.find(b"\0", n)
    return strtab[n:end].decode("latin1")


TYPES = {0: "NULL", 1: "PROGBITS", 2: "SYMTAB", 3: "STRTAB", 4: "RELA", 5: "HASH",
         6: "DYNAMIC", 7: "NOTE", 8: "NOBITS", 9: "REL", 10: "SHLIB", 11: "DYNSYM",
         14: "INIT_ARRAY", 15: "FINI_ARRAY", 16: "PREINIT_ARRAY", 17: "GROUP",
         18: "SYMTAB_SHNDX"}

print("%-28s %-14s %14s %12s %12s" % ("Name", "Type", "Addr", "Offset", "Size"))
print("-" * 86)
for i in range(e_shnum):
    n, t, f, a, o, s, l, inf, al, es = secs[i]
    print("%-28s %-14s 0x%012x %12d %12d" % (sn(i), TYPES.get(t, str(t)), a, o, s))

print()
print("== DWARF 相关 ==")
for i in range(e_shnum):
    nm = sn(i)
    if nm.startswith(".debug") or nm.startswith(".zdebug"):
        print("  %-24s addr=0x%x off=%d size=%d" % (nm, secs[i][3], secs[i][4], secs[i][5]))
print()
print("total sections =", e_shnum)
