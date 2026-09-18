# -*- coding: utf-8 -*-
"""可信版反汇编：把 .text 的 bl/b 目标同时解析到 PLT 导入符号 + 本地函数符号。

用法: python tools/disasm_truth.py [outfile]
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

# --- dynsym ---
dynsym = by[".dynsym"]
dynstr = by[".dynstr"]
entsize = dynsym[9] or 24
sym_names = []
for i in range(dynsym[5] // entsize):
    e = struct.unpack_from(endian + "IBBHQQ", data, dynsym[4] + i * entsize)
    off = dynstr[4] + e[0]
    fin = data.index(b"\0", off)
    sym_names.append(data[off:fin].decode(errors="replace"))

# --- .rela.plt: got -> name, and PLT stub address ---
rela = by.get(".rela.plt")
got_plt_syms = {}
if rela:
    es = rela[9] or 24
    for i in range(rela[5] // es):
        e = struct.unpack_from(endian + "QQq", data, rela[4] + i * es)
        r_offset, r_info = e[0], e[1]
        idx = r_info >> 32
        if idx < len(sym_names):
            got_plt_syms[r_offset] = sym_names[idx]

plt_sec = by[".plt"]
plt_start = plt_sec[3]
plt_map = {}
for n, ga in enumerate(sorted(got_plt_syms.keys())):
    plt_map[plt_start + 32 + n * 16] = got_plt_syms[ga] + " (PLT)"

# --- local funcs ---
symtab_name = ".symtab"
if symtab_name in by:
    dsym = by[symtab_name]
    dstr = by[".strtab"]
else:
    dsym = dynsym
    dstr = dynstr
funcs = []
for off in range(0, dsym[5], 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
        endian + "IBBHQQ", data, dsym[4] + off)
    if st_name == 0 or st_value == 0:
        continue
    e = dstr[4] + st_name
    fin = data.index(b"\0", e)
    name = data[e:fin].decode(errors="replace")
    if name and (st_info & 0xF) == 2:
        funcs.append((st_value, st_size, name))
funcs.sort()
by_addr = {a: (sz, nm) for a, sz, nm in funcs}


def symname(a):
    if a in plt_map:
        return plt_map[a]
    if a in by_addr:
        return by_addr[a][1]
    return "sub_%x" % a


md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def disasm(addr, size, label=""):
    print("\n=== %s @ 0x%x (size=0x%x) ===" % (label or symname(addr), addr, size))
    fo = text[4] + (addr - text[3])
    for ins in md.disasm(data[fo:fo + size], addr):
        ann = ""
        if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("#"):
            try:
                ann = "  ; " + symname(int(ins.op_str.lstrip("#"), 0))
            except Exception:
                pass
        print("  0x%x: %-9s %s%s" % (ins.address, ins.mnemonic, ins.op_str, ann))


print("== 结论性符号 ==")
for a in (0x683510, 0x68365c, 0x66ac5c, 0x66c12c, 0x5fa168, 0x5f9f78, 0x682858,
          0x6838d4, 0x6838f4, 0x683e08, 0x683e0c, 0x74c604, 0x74c5e4, 0x74c06c):
    print("  0x%-8x -> %s" % (a, symname(a)))

disasm(0x683510, 0x150, "lpd_listen_create(疑似)")
disasm(0x66ac5c, 0x120, "net_socket_create_tcpserver 头部")
disasm(0x66b1f0, 0xc0, "net_socket_create_tcpserver listen 段")
disasm(0x66c12c, 0x1c0, "net_socket_accept_connection 头部")
