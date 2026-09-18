# -*- coding: utf-8 -*-
# Step 4 收尾：确认引擎上下文全局指针 [0xa76000+0x110] 的符号名，
# 并反汇编 act_init_step1 (0x505f38) 确认其内部调用 engine_hal_* 的链路。
import sys, struct
sys.stdout = open(r"runtime\eng_ctx.txt", "w", encoding="utf-8", errors="replace")

ELF = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
data = open(ELF, "rb").read()

# ---- ELF 基础解析 ----
assert data[:4] == b"\x7fELF"
is64 = data[4] == 2
le = data[5] == 1
E = "<" if le else ">"
e_shoff = struct.unpack_from(E + "Q", data, 0x28)[0] if is64 else struct.unpack_from(E + "I", data, 0x20)[0]
e_shentsize = struct.unpack_from(E + "H", data, 0x3A)[0] if is64 else struct.unpack_from(E + "H", data, 0x2E)[0]
e_shnum = struct.unpack_from(E + "H", data, 0x3C)[0] if is64 else struct.unpack_from(E + "H", data, 0x30)[0]
e_shstrndx = struct.unpack_from(E + "H", data, 0x3E)[0] if is64 else struct.unpack_from(E + "H", data, 0x32)[0]

def sh(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(E + "IIQQQQIIQQ", data, off) if is64 else struct.unpack_from(E + "IIIIIIIIII", data, off)

shstr = data[sh(e_shstrndx)[4]:sh(e_shstrndx)[4]+sh(e_shstrndx)[5]]
sec = {}
for i in range(e_shnum):
    s = sh(i)
    name = shstr[s[0]:shstr.find(b"\0", s[0])].decode("ascii", "replace")
    sec[name] = s

def v2off(va):
    for n, s in sec.items():
        if s[1] == 1:  # PROGBITS under PT_LOAD; also handle NOBITS
            continue
    best = None
    for n, s in sec.items():
        if s[1] == 1 or s[1] == 8:  # PROGBITS / NOBITS
            if s[3] <= va < s[3] + (s[5] if s[1] == 1 else 0):
                best = s
    # fallback: 用 LOAD 段映射
    for n, s in sec.items():
        if s[3] <= va < s[3] + s[5] and (s[1] == 1 or s[1] == 8):
            return n, s[3], va - s[3]
    return None, None, None

print("== 1) 全局指针 [0xa76110] 所在段的符号 ==")
# 0xa76000 + 0x110 = 0xa76110
secname, secva, off = v2off(0xa76110)
print(f"0xa76110 -> section {secname} va=0x{secva:x} off=0x{off:x}")
if secname and secname != ".bss":
    raw = data[sec[secname][4]+off: sec[secname][4]+off+8]
    print("bss 前 8 字节 (若 .data 则为文件初值):", raw.hex())
else:
    print("位于 .bss（无文件初值，运行时初始化）")

# 用 symtab 找 0xa76000~0xa76400 范围内符号
print("\n== 2) symtab 中 0xa76000~0xa76400 范围符号 ==")
def read_symtab(tab_name, str_name):
    ts = sec[tab_name]; ss = sec[str_name]
    entsize = 24 if is64 else 16
    n = ts[5] // entsize
    strtab = data[ss[4]:ss[4]+ss[5]]
    out = []
    for i in range(n):
        e = data[ts[4]+i*entsize:ts[4]+(i+1)*entsize]
        if is64:
            name_off, info, other, shndx, value, size = struct.unpack_from(E+"IBBHQQ", e, 0)
        else:
            name_off, value, size, info, other, shndx = struct.unpack_from(E+"IIIBBH", e, 0)
        if 0 < shndx < 0xff00 and value != 0:
            nm = strtab[name_off:strtab.find(b"\0", name_off)].decode("ascii", "replace")
            out.append((value, nm, size, shndx))
    return out

for tname, sname in ((".symtab", ".strtab"), (".dynsym", ".dynstr")):
    if tname not in sec:
        continue
    print(f"\n-- {tname} --")
    for value, nm, size, shndx in read_symtab(tname, sname):
        if 0xa76000 <= value <= 0xa76400 and nm:
            print(f"  0x{value:x} (size 0x{size:x}, shndx {shndx})  {nm}")

print("\n== 3) act_init_step1 (0x505f38) 反汇编 0x300 字节，标注 bl 目标符号 ==")
try:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
except ImportError:
    cs_ok = False
else:
    cs_ok = True

syms = read_symtab(".symtab", ".strtab")
dyms = read_symtab(".dynsym", ".dynstr")
def symname(addr):
    for value, nm, size, shndx in syms + dyms:
        if value == addr:
            return nm
    return None

if cs_ok:
    text = sec[".text"]
    code = data[text[4]:text[4]+text[5]]
    base = text[3]
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for ins in md.disasm(code[0x505f38-base:0x505f38-base+0x300], base + (0x505f38-base)):
        extra = ""
        if ins.mnemonic in ("bl", "b", "b.eq", "b.ne", "adrp", "blr"):
            if ins.mnemonic in ("bl", "b"):
                tgt = ins.address + 4 + int(ins.op_str.lstrip("#"), 16)
                nm = symname(tgt)
                extra = f"  -> {nm}" if nm else ""
            if ins.mnemonic == "adrp":
                extra = f"  (page)"
        print(f"  0x{ins.address:x}: {ins.mnemonic:8s} {ins.op_str}{extra}")
else:
    print("capstone 不可用")