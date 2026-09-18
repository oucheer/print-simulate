#!/usr/bin/env python3
"""elf_scan.py — mfp.afx 静态分析小工具（AArch64 ELF，无外部依赖）

用法:
  python tools/elf_scan.py sections
  python tools/elf_scan.py callers 0x66ac5c 0x6838f4 ...
  python tools/elf_scan.py refs 0x6838f4 0x68365c ...      # ADRP+ADD 取地址（函数指针注册）
  python tools/elf_scan.py strings lpd 9100 printcap       # 正则/子串搜索 .rodata
  python tools/elf_scan.py funcs 0x66ac5c                 # 打印该地址所在“函数”的完整反汇编（粗略边界）
  python tools/elf_scan.py disas 0x66b650 0x120           # 指定 VA 起反汇编 N 字节
"""
import struct, sys, re

PATH = r"d:\Apps\codex\files\simulate\mfp.afx"


class Elf:
    def __init__(self, path=PATH):
        self.d = open(path, "rb").read()
        d = self.d
        e_phoff, = struct.unpack_from("<Q", d, 0x20)
        e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)
        e_shoff, = struct.unpack_from("<Q", d, 0x28)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", d, 0x3a)
        self.loads = []
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            p_type, = struct.unpack_from("<I", d, off)
            p_offset, p_vaddr, _p, p_filesz, _m = struct.unpack_from("<QQQQQ", d, off + 8)
            if p_type == 1:
                self.loads.append((p_offset, p_vaddr, p_filesz))
        shstr_va, = struct.unpack_from("<Q", d, e_shoff + e_shstrndx * e_shentsize + 0x18)

        def shname(o):
            e = d.index(b"\0", shstr_va + o)
            return d[shstr_va + o:e].decode()

        self.secs = {}
        for i in range(e_shnum):
            off = e_shoff + i * e_shentsize
            nameoff, sh_type = struct.unpack_from("<II", d, off)
            sh_offset, sh_size = struct.unpack_from("<QQ", d, off + 0x18)
            entsz, = struct.unpack_from("<Q", d, off + 0x38)
            self.secs[shname(nameoff)] = (sh_type, sh_offset, sh_size, entsz)

    def va2off(self, va):
        for o, v, sz in self.loads:
            if v <= va < v + sz:
                return o + (va - v)
        return None

    def off2va(self, off):
        for o, v, sz in self.loads:
            if o <= off < o + sz:
                return v + (off - o)
        return None

    def text(self):
        _, off, size, _ = self.secs[".text"]
        return off, size, self.off2va(off)

    def symbols(self):
        out = []
        _, off, size, entsz = self.secs.get(".symtab", (0, 0, 0, 24))
        _, soff, ssize, _ = self.secs.get(".strtab", (0, 0, 0, 0))
        entsz = entsz or 24
        for k in range(size // entsz):
            p = off + k * entsz
            nm, info_, other, shndx, val, sz = struct.unpack_from("<IBBHQQ", self.d, p)
            if nm == 0:
                continue
            e = self.d.index(b"\0", soff + nm)
            out.append((val, self.d[soff + nm:e].decode("utf-8", "replace"), sz))
        return out

    def nearest_sym(self, va, syms=None):
        syms = syms if syms is not None else self.symbols()
        best = None
        for val, nm, sz in syms:
            if not nm or nm.startswith("$") or nm.endswith(".c"):
                continue
            if val <= va and (best is None or val > best[0]):
                if sz and va >= val + sz:
                    continue
                best = (val, nm, sz)
        return best


def bl_targets(e):
    off, size, tva = e.text()
    buf = e.d[off:off + size]
    res = []
    for k in range(0, len(buf) - 3, 4):
        w, = struct.unpack_from("<I", buf, k)
        va = tva + k
        if (w & 0xFC000000) == 0x94000000:
            imm = w & 0x03FFFFFF
            if imm & 0x02000000:
                imm -= 0x04000000
            res.append(("BL", va, va + imm * 4))
        elif (w & 0xFC000000) == 0x14000000:
            imm = w & 0x03FFFFFF
            if imm & 0x02000000:
                imm -= 0x04000000
            res.append(("B", va, va + imm * 4))
    return res


def adrp_add_refs(e):
    """粗略跟踪 ADRP+ADD，返回 (指令VA, 计算出的地址) 列表"""
    off, size, tva = e.text()
    buf = e.d[off:off + size]
    regs = {}
    out = []
    for k in range(0, len(buf) - 3, 4):
        w, = struct.unpack_from("<I", buf, k)
        va = tva + k
        if (w & 0x9F000000) == 0x90000000:  # adrp
            rd = w & 0x1F
            immlo = (w >> 29) & 3
            immhi = (w >> 5) & 0x7FFFF
            imm = (immhi << 2) | immlo
            if imm & (1 << 20):
                imm -= (1 << 21)
            page = (va & ~0xFFF) + (imm << 12)
            regs[rd] = page
        elif (w & 0xFF800000) == 0x91000000:  # add xd, xn, #imm12
            rd = w & 0x1F
            rn = (w >> 5) & 0x1F
            imm12 = (w >> 10) & 0xFFF
            shift = (w >> 22) & 3
            if rn in regs:
                v = regs[rn] + (imm12 << (12 if shift == 1 else 0))
                regs[rd] = v
                out.append((va, v))
        elif (w & 0xFF800000) == 0xF9400000:  # ldr xd,[xn,#imm]
            rn = (w >> 5) & 0x1F
            if rn in regs:
                out.append((va, regs[rn]))
    return out


def disas(e, va, n, syms=None):
    """capstone 反汇编，带符号/字符串标注"""
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
        md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        md.detail = True
    except Exception:
        return disas_raw(e, va, n)
    off = e.va2off(va)
    code = e.d[off:off + n]
    bysym = {}
    if syms:
        for val, nm, sz in syms:
            if nm and not nm.startswith("$"):
                bysym.setdefault(val, nm)
    lines = []
    for ins in md.disasm(code, va):
        note = ""
        m = ins.mnemonic
        ops = ins.op_str
        if m in ("bl", "b", "b.eq", "b.ne", "b.lt", "b.gt", "b.le", "b.ge",
                 "b.hi", "b.ls", "b.hs", "b.cc", "b.cs") and ops.startswith("#"):
            try:
                t = int(ops[1:], 16)
                if t in bysym:
                    note = "  ; " + bysym[t]
                elif e.va2off(t) is not None and syms:
                    ns = e.nearest_sym(t, syms)
                    if ns:
                        note = "  ; %s+%#x" % (ns[1], t - ns[0])
            except ValueError:
                pass
        if m in ("adrp", "add") and ops.startswith("x") is False:
            pass
        # 标注 ADRP/ADD 的目标落在 .rodata 的字符串
        lines.append("  %#010x: %-8s %s%s" % (ins.address, m, ops, note))
    return "\n".join(lines)


def disas_raw(e, va, n):
    off = e.va2off(va)
    buf = e.d[off:off + n]
    out = []
    for k in range(0, len(buf) - 3, 4):
        w, = struct.unpack_from("<I", buf, k)
        mnem, tgt = "raw", ""
        if (w & 0xFC000000) in (0x94000000, 0x14000000):
            imm = w & 0x03FFFFFF
            if imm & 0x02000000:
                imm -= 0x04000000
            mnem = "bl" if (w & 0xFC000000) == 0x94000000 else "b"
            tgt = " %#x" % (va + k + imm * 4)
        elif w == 0xD65F03C0:
            mnem = "ret"
        out.append("  %#x: %#010x  %s%s" % (va + k, w, mnem, tgt))
    return "\n".join(out)


def strings(e, pats, limit=80):
    rx = re.compile(pats, re.I)
    d = e.d
    seen = 0
    for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
        s = m.group().decode()
        if rx.search(s):
            va = e.off2va(m.start())
            if va is None:
                continue
            print("%#x  %s" % (va, s[:160]))
            seen += 1
            if seen >= limit:
                return


def main():
    e = Elf()
    cmd = sys.argv[1]
    if cmd == "sections":
        for n, (t, o, s, es) in e.secs.items():
            print("%-20s type=%-2d off=%#x size=%#x" % (n, t, o, s))
    elif cmd == "callers":
        tgts = {int(x, 16) for x in sys.argv[2:]}
        syms = e.symbols()
        names = {v: n for v, n, _s in syms if v in tgts}
        for kind, va, tgt in bl_targets(e):
            if tgt in tgts:
                ns = e.nearest_sym(va, syms)
                where = "(in %s+%#x)" % (ns[1], va - ns[0]) if ns else ""
                print("%s from %#x -> %#x %s  %s" % (kind, va, tgt, names.get(tgt, "?"), where))
    elif cmd == "refs":
        tgts = {int(x, 16) for x in sys.argv[2:]}
        syms = e.symbols()
        for va, v in adrp_add_refs(e):
            if v in tgts:
                ns = e.nearest_sym(va, syms)
                print("%#x -> %#x  (in %s+%#x)" % (va, v, ns[1], va - ns[0]) if ns else "%#x -> %#x" % (va, v))
    elif cmd == "strings":
        strings(e, sys.argv[2] if len(sys.argv) > 2 else "lpd")
    elif cmd == "disas":
        print(disas(e, int(sys.argv[2], 16), int(sys.argv[3], 16), e.symbols()))
    elif cmd == "funcs":
        va = int(sys.argv[2], 16)
        n = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x200
        ns = e.nearest_sym(va, e.symbols())
        if ns:
            print(";; %s @%#x size=%#x" % (ns[1], ns[0], ns[2]))
        print(disas(e, va, n, e.symbols()))
    elif cmd == "sym":
        syms = e.symbols()
        for s in syms:
            if s[1] and sys.argv[2].lower() in s[1].lower():
                print("%#x size=%#x %s" % (s[0], s[2], s[1]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()