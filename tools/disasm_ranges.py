# -*- coding: utf-8 -*-
"""通用 xref + 区间反汇编工具（符号解析到 PLT 导入 + 本地函数）。

用法:
  python tools/disasm_ranges.py out.txt xref:0x68365c,0x683e0c
  python tools/disasm_ranges.py out.txt dis:0x68365c:0x400:lpd_dispatch_thread
  python tools/disasm_ranges.py out.txt str:0x85a000+0xf10
可混合多个动作。
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"

argv = [a for a in sys.argv[1:]]
outfile = None
actions = []
for a in argv:
    if ":" in a and not a.startswith("0x"):
        actions.append(a)
    elif outfile is None:
        outfile = a
    else:
        actions.append(a)
if outfile:
    sys.stdout = open(outfile, "w", encoding="utf-8")

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

dynsym = by[".dynsym"]
dynstr = by[".dynstr"]
entsize = dynsym[9] or 24
sym_names = []
for i in range(dynsym[5] // entsize):
    e = struct.unpack_from(endian + "IBBHQQ", data, dynsym[4] + i * entsize)
    off = dynstr[4] + e[0]
    fin = data.index(b"\0", off)
    sym_names.append(data[off:fin].decode(errors="replace"))

rela = by.get(".rela.plt")
got_plt_syms = {}
if rela:
    es = rela[9] or 24
    for i in range(rela[5] // es):
        e = struct.unpack_from(endian + "QQq", data, rela[4] + i * es)
        idx = e[1] >> 32
        if idx < len(sym_names):
            got_plt_syms[e[0]] = sym_names[idx]

plt_sec = by[".plt"]
plt_map = {}
for n, ga in enumerate(sorted(got_plt_syms.keys())):
    plt_map[plt_sec[3] + 32 + n * 16] = got_plt_syms[ga] + "(plt)"

if ".symtab" in by:
    dsym, dstr = by[".symtab"], by[".strtab"]
else:
    dsym, dstr = dynsym, dynstr
funcs = []
for off in range(0, dsym[5], 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
        endian + "IBBHQQ", data, dsym[4] + off)
    if st_name == 0 or st_value == 0:
        continue
    e = dstr[4] + st_name
    fin = data.index(b"\0", e)
    nm = data[e:fin].decode(errors="replace")
    if nm and (st_info & 0xF) == 2:
        funcs.append((st_value, st_size, nm))
funcs.sort()
by_addr = {a: (sz, nm) for a, sz, nm in funcs}


def symname(a):
    if a in plt_map:
        return plt_map[a]
    if a in by_addr:
        return by_addr[a][1]
    return "sub_%x" % a


def owner(a):
    """最接近且 <= a 的本地函数"""
    best = None
    for fa, sz, nm in funcs:
        if fa <= a:
            if best is None or fa > best[0]:
                best = (fa, nm)
        else:
            break
    return best[1] if best else "?"


md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
insns = list(md.disasm(data[text[4]:text[4] + text[5]], text[3]))
addr2idx = {ins.address: i for i, ins in enumerate(insns)}


def dump(addr, size, label=""):
    print("\n=== %s @ 0x%x (size=0x%x) ===" % (label or symname(addr), addr, size))
    for ins in md.disasm(data[text[4] + (addr - text[3]):][:size], addr):
        ann = ""
        if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("#"):
            try:
                ann = "  ; " + symname(int(ins.op_str.lstrip("#"), 0))
            except Exception:
                pass
        print("  0x%x: %-9s %s%s" % (ins.address, ins.mnemonic, ins.op_str, ann))


for act in actions:
    kind, _, rest = act.partition(":")
    if kind == "dis":
        parts = rest.split(":")
        addr = int(parts[0], 0)
        size = int(parts[1], 0) if len(parts) > 1 else 0x100
        label = parts[2] if len(parts) > 2 else ""
        dump(addr, size, label)
    elif kind == "xref":
        for tgt_s in rest.split(","):
            tgt = int(tgt_s, 0)
            print("\n=== xref -> 0x%x (%s) ===" % (tgt, symname(tgt)))
            pending = {}
            hits = []
            for ins in insns:
                if ins.mnemonic == "adrp":
                    try:
                        pending[ins.op_str.split(",")[0].strip()] = int(
                            ins.op_str.split("#")[1], 0)
                    except Exception:
                        pass
                elif ins.mnemonic in ("add",):
                    p = ins.op_str.split(",")
                    if len(p) >= 3 and p[1].strip() in pending:
                        try:
                            val = pending[p[1].strip()] + int(p[2].split("#")[1], 0)
                        except Exception:
                            continue
                        if val == tgt:
                            hits.append(ins.address)
                        del pending[p[1].strip()]
                elif ins.mnemonic in ("bl", "ldr", "str"):
                    pending = {}
            for h in sorted(hits):
                ctx = []
                for j in range(max(0, addr2idx[h] - 6), min(len(insns), addr2idx[h] + 5)):
                    i2 = insns[j]
                    m = "  >> " if i2.address == h else "     "
                    an = ""
                    if i2.mnemonic in ("bl", "b") and i2.op_str.startswith("#"):
                        an = "  ; " + symname(int(i2.op_str.lstrip("#"), 0))
                    ctx.append("%s0x%x: %-9s %s%s" % (m, i2.address, i2.mnemonic, i2.op_str, an))
                print("  --- hit 0x%x in %s(0x%x) ---" % (h, owner(h), 0))
                for c in ctx:
                    print(c)
    elif kind == "callers":
        # 扫所有 bl，找出调用指定地址的位置
        for tgt_s in rest.split(","):
            tgt = int(tgt_s, 0)
            print("\n=== callers of 0x%x (%s) ===" % (tgt, symname(tgt)))
            found = False
            for i, ins in enumerate(insns):
                if ins.mnemonic != "bl" or not ins.op_str.startswith("#"):
                    continue
                try:
                    if int(ins.op_str.lstrip("#"), 0) != tgt:
                        continue
                except Exception:
                    continue
                found = True
                print("  0x%x  in %s" % (ins.address, owner(ins.address)))
            if not found:
                print("  (none via direct bl)")
    elif kind == "ptr":
        # 在 .rodata/.data/.bss 中搜 8 字节小端等于目标地址的位置（函数指针表）
        for tgt_s in rest.split(","):
            tgt = int(tgt_s, 0)
            needle = struct.pack("<Q", tgt)
            print("\n=== ptr table refs to 0x%x (%s) ===" % (tgt, symname(tgt)))
            found = False
            for i in range(e_shnum):
                sec = secs[i]
                if not sec[4] or not sec[5] or (sec[2] & 0x2):  # 跳过 PROGBITS 之外
                    pass
                if sec[2] not in (1, 3) or sec[4] == 0:
                    continue
                d = data[sec[4]:sec[4] + sec[5]]
                idx = 0
                while True:
                    j = d.find(needle, idx)
                    if j < 0:
                        break
                    print("  0x%x  [%s]" % (sec[3] + j, sn(i)))
                    found = True
                    idx = j + 1
            if not found:
                print("  (no pointer-table refs)")
    elif kind == "str":
        for tok in rest.split(","):
            if "+" in tok:
                base, off = tok.split("+")
                v = int(base, 0) + int(off, 0)
            else:
                v = int(tok, 0)
            s = None
            secname = "?"
            for i in range(e_shnum):
                sec = secs[i]
                if sec[3] and sec[3] <= v < sec[3] + sec[5]:
                    o = sec[4] + (v - sec[3])
                    secname = sn(i)
                    try:
                        en = data.index(b"\0", o)
                        s = data[o:en].decode("utf-8", "replace")
                    except ValueError:
                        s = "<no nul>"
            print("  0x%x: %r  [%s]" % (v, s, secname))
