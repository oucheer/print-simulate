# -*- coding: utf-8 -*-
"""全量反汇编 LPD 关键函数 + 字符串 xref 定位 notify 路径。
用法: python tools/disasm_lpd_full.py [--xref-only]
"""
import struct
import sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM


def out(s):
    print(s)
    sys.stdout.flush()

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
XREF_ONLY = "--xref-only" in sys.argv

# 非选项参数作为输出文件（绕开 shell 重定向问题）
for _a in sys.argv[1:]:
    if not _a.startswith("--"):
        sys.stdout = open(_a, "w", encoding="utf-8")
        break

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

# dynsym -> 符号表（函数名）
symtab_name = ".dynsym" if ".dynsym" in by else ".symtab"
dsym = by[symtab_name]
dstr = by[".dynstr" if symtab_name == ".dynsym" else ".strtab"]
syms = {}  # addr -> name
for off in range(0, dsym[5], 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
        endian + "IBBHQQ", data, dsym[4] + off)
    if st_name == 0 or st_value == 0:
        continue
    e = dstr[4] + st_name
    end = data.index(b"\0", e)
    name = data[e:end].decode(errors="replace")
    if name and st_info & 0xF == 2:  # STT_FUNC
        syms.setdefault(st_value, name)

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def disasm(addr, size, label=""):
    out("\n=== %s @ 0x%x (size=0x%x) ===" % (label or syms.get(addr, "?"), addr, size))
    fo = text[4] + (addr - text[3])
    code = data[fo:fo + size]
    for ins in md.disasm(code, addr):
        ann = ""
        if ins.mnemonic == "bl":
            try:
                tgt = int(ins.op_str.lstrip("#"), 0)
                ann = "  ; %s" % syms.get(tgt, "sub_%x" % tgt)
            except Exception:
                pass
        out("  0x%x: %-9s %s%s" % (ins.address, ins.mnemonic, ins.op_str, ann))


# ---------- 1. 字符串 xref ----------
rodata = by[".rodata"]
rod_data = data[rodata[4]:rodata[4] + rodata[5]]
targets = {}
for s in (b"notify lpd switch", b"lpd switch", b"notify ipp switch"):
    idx = 0
    while True:
        i = rod_data.find(s, idx)
        if i < 0:
            break
        va = rodata[3] + i
        targets[va] = s.decode()
        idx = i + 1

print("=== rodata string targets ===")
for va, name in sorted(targets.items()):
    out("  0x%x: %s" % (va, name))

if XREF_ONLY:
    sys.exit(0)

out("\n=== .text xref scan (adrp+add) ===")
insns = []
try:
    for ins in md.disasm(data[text[4]:text[4] + text[5]], text[3]):
        insns.append(ins)
        if len(insns) % 200000 == 0:
            out("  ...scanned %d insns" % len(insns))
except Exception as e:
    out("  disasm error at %d insns: %s" % (len(insns), e))
pending = {}
hits = []
for ins in insns:
    if ins.mnemonic == "adrp":
        try:
            reg = ins.op_str.split(",")[0].strip()
            page = int(ins.op_str.split("#")[1], 0)
            pending[reg] = (ins.address, page)
        except Exception:
            pass
    elif ins.mnemonic in ("add",):
        parts = ins.op_str.split(",")
        if len(parts) >= 3:
            dreg = parts[0].strip()
            sreg = parts[1].strip()
            if sreg in pending:
                try:
                    off = int(parts[2].split("#")[1], 0)
                except Exception:
                    continue
                adr, page = pending[sreg]
                val = page + off
                if val in targets:
                    hits.append((ins.address, val, targets[val]))
                del pending[sreg]
    elif ins.mnemonic == "bl":
        pending = {}

caller_funcs = set()
for addr, sva, name in sorted(hits):
    # 找到所属函数（在 syms 中 <= addr 的最大函数地址）
    f = None
    for fa, fn in syms.items():
        if fa <= addr:
            if f is None or fa > f[0]:
                f = (fa, fn)
    fn = f[1] if f else "?"
    out("  0x%x in %s ref 0x%x (%s)" % (addr, fn, sva, name))
    caller_funcs.add(f[0] if f else addr)

# ---------- 2. 全量 dump ----------
out("\n=== resolve call targets ===")
for a in (0x61fa9c, 0x61a758, 0x5fa168, 0x682858, 0x683510, 0x68365c,
          0x683e0c, 0x68236c, 0x684068, 0x5fdac8):
    out("  0x%x -> %s" % (a, syms.get(a, "sub_%x" % a)))

# 完整 setter（notify 路径）
try:
    disasm(0x61fa9c, 0x614, "netdata_set_lpd_switch")
    disasm(0x68365c, 0x7b0, "lpd_thread")
    disasm(0x683510, 0x14c, "lpd_listen_struct")
except Exception as e:
    out("disasm error: %s" % e)
