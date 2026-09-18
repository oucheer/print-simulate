# -*- coding: utf-8 -*-
"""Step 4: 提取 mfp.afx 中 pi_engfw_*/pi_eng*/engine 相关符号与引用点
1) 符号表过滤（.symtab 优先，退 .dynsym）
2) .rodata 字符串扫描（pi_eng / engfw / engine）
3) .text 中 bl 到引擎函数地址的调用点
4) .text 中 adrp+add 引用引擎字符串的引用点
"""
import struct, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
KEYS = ("pi_eng", "engfw", "_engine", "engine_", "SENSO", "feeder", "ENGINE")
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
def rs(sec, off):
    d = data[sec[4]:sec[4] + sec[5]]
    try:
        e = d.index(b"\0", off)
    except ValueError:
        return d[off:].decode(errors="replace")
    return d[off:e].decode(errors="replace")
def vaddr2off(vaddr):
    for i in range(e_shnum):
        s = secs[i]
        if s[3] <= vaddr < s[3] + s[5] and s[4] != 0:
            return s[4] + (vaddr - s[3])
    return None

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

print("=" * 70)
print("PART A: 符号表过滤")
print("=" * 70)
found = {}
for tab, strn, tdesc in ((".symtab", ".strtab", "static"), (".dynsym", ".dynstr", "dyn")):
    if tab not in by or strn not in by:
        continue
    symsec = by[tab]; strsec = by[strn]
    if symsec[5] == 0:
        continue
    entsize = symsec[9] or 24
    for i in range(symsec[5] // entsize):
        e = struct.unpack_from(endian + "IBBHQQ", data, symsec[4] + i * entsize)
        nm = rs(strsec, e[0])
        if nm == "":
            continue
        low = nm.lower()
        if any(k in low for k in ("pi_eng", "engfw")) or low in ("engine", "ENGINE"):
            found.setdefault(low, []).append((e[4], tdesc))
            print("  %-10s 0x%x  %s" % (tdesc, e[4], nm))

print()
print("=" * 70)
print("PART B: .rodata/.data 字符串扫描")
print("=" * 70)
syms_str = set()
for secname in (".rodata", ".data"):
    if secname not in by:
        continue
    s = by[secname]
    blk = data[s[4]:s[4] + s[5]]
    pos = 0
    while True:
        pos = blk.find(b"pi_eng", pos)
        if pos < 0:
            break
        start = blk.rfind(b"\0", 0, pos)
        e = blk.find(b"\0", pos)
        sval = blk[start + 1:e].decode("utf-8", "replace")
        va = s[3] + pos
        syms_str.add(va)
        print("  0x%x: %r" % (va, sval))
        pos = e

print()
print("=" * 70)
print("PART C: .text 中 bl 到引擎符号地址的调用点")
print("=" * 70)
text = by[".text"]
insns = list(md.disasm(data[text[4]:text[4] + text[5]], text[3]))
addr2name = {}
for low, lst in found.items():
    for va, t2 in lst:
        addr2name[va] = low
calls = []
for ins in insns:
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str.strip("#"), 0)
        except Exception:
            continue
        if tgt in addr2name:
            calls.append((ins.address, tgt, addr2name[tgt]))
for a, t, n in calls:
    print("  0x%x  bl  0x%x  (%s)" % (a, t, n))
print("  calls total: %d" % len(calls))

print()
print("=" * 70)
print("PART D: .text 中 adrp+add 引用引擎字符串地址")
print("=" * 70)
pending = {}
strhits = []
for ins in insns:
    if ins.mnemonic == "adrp":
        try:
            reg = ins.op_str.split(",")[0].strip()
            page = int(ins.op_str.split("#")[1], 0)
            pending[reg] = (ins.address, page)
        except Exception:
            pass
    elif ins.mnemonic in ("add", "adds"):
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
                if val in syms_str:
                    strhits.append((ins.address, val))
                del pending[sreg]
    elif ins.mnemonic == "bl":
        pending = {}
for a, v in sorted(strhits):
    print("  0x%x  ref 0x%x" % (a, v))
print("  refs total: %d" % len(strhits))

print()
print("=" * 70)
print("PART F: .rela.plt/.rela.dyn 中引擎符号 -> PLT 地址")
print("=" * 70)
got2sym = {}
all_syms = {}
if ".dynsym" in by and ".dynstr" in by:
    symsec = by[".dynsym"]; strsec = by[".dynstr"]
    entsize = symsec[9] or 24
    for i in range(symsec[5] // entsize):
        e = struct.unpack_from(endian + "IBBHQQ", data, symsec[4] + i * entsize)
        nm = rs(strsec, e[0])
        if nm:
            all_syms[i] = (nm, e[4])
for relaname in (".rela.plt", ".rela.dyn"):
    if relaname not in by:
        continue
    relsec = by[relaname]
    es = relsec[9] or 24
    print("  -- %s --" % relaname)
    for i in range(relsec[5] // es):
        e = struct.unpack_from(endian + "QQq", data, relsec[4] + i * es)
        r_offset, r_info = e[0], e[1]
        sym_idx = r_info >> 32
        if sym_idx in all_syms:
            nm, symva = all_syms[sym_idx]
            low = nm.lower()
            if "eng" in low or "engine" in low:
                got2sym[r_offset] = nm
                print("  0x%x -> %s" % (r_offset, nm))

# 从 GOT 推导 PLT 桩地址
print()
print("  PLT 桩推算（.plt 每 16B 一个槽）: ")
if ".plt" in by and ".got.plt" in by:
    plt_sec = by[".plt"]
    got_plt_addrs = sorted(g for g in got2sym if ".got.plt" and True)
    print("  (需要 .got.plt 起始推算槽位，见下)")
print("  engine syms via rela: %d" % len(got2sym))

print()
print("=" * 70)
print("PART G: 引擎日志字符串引用点(宽松 adrp+add 配对)")
print("=" * 70)
text = by[".text"]
pending = {}
strhits2 = []
tt = sorted(syms_str)
for ins in insns:
    if ins.mnemonic == "adrp":
        try:
            reg = ins.op_str.split(",")[0].strip()
            page = int(ins.op_str.split("#")[1], 0)
        except Exception:
            continue
        pending[reg] = (ins.address, page)
    elif ins.mnemonic == "add":
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
                if val in syms_str:
                    strhits2.append((ins.address, val))
                # 不删除，允许后续覆盖；但避免重复记录
for a, v in sorted(strhits2):
    print("  0x%x  ref 0x%x" % (a, v))
print("  refs total: %d" % len(strhits2))
idx_of = {ins.address: i for i, ins in enumerate(insns)}
seen = set()
for a, t, n in calls[:40]:
    if n in seen:
        continue
    seen.add(n)
    # 前向找最近函数头（stp x29,x30，或 mrs/eor 栈保护特征）
    i = idx_of[a]
    head = None
    for j in range(max(0, i - 260), i):
        p = insns[j]
        if p.mnemonic == "stp" and "x29" in p.op_str and ("x30" in p.op_str or "sp]" in p.op_str):
            head = p.address
            break
    print("  %-24s call@0x%x head~0x%x" % (n, a, head if head else 0))