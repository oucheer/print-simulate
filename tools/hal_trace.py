# -*- coding: utf-8 -*-
# Step 5 探路：反汇编 engine_hal_* 8 个函数，解析 bl 目标符号与 PLT/GOT 外部依赖，
# 确定 Virtual Engine 注入通道。
import sys, struct
sys.stdout = open(r"runtime\hal_trace.txt", "w", encoding="utf-8", errors="replace")

ELF = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
data = open(ELF, "rb").read()

E = "<"
e_shoff = struct.unpack_from(E + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(E + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(E + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(E + "H", data, 0x3E)[0]

def sh(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(E + "IIQQQQIIQQ", data, off)

shstr = data[sh(e_shstrndx)[4]:sh(e_shstrndx)[4]+sh(e_shstrndx)[5]]
sec = {}
for i in range(e_shnum):
    s = sh(i)
    name = shstr[s[0]:shstr.find(b"\0", s[0])].decode("ascii", "replace")
    sec[name] = s

def read_symtab(tab, strn):
    ts = sec[tab]; ss = sec[strn]
    entsize = 24
    n = ts[5] // entsize
    strtab = data[ss[4]:ss[4]+ss[5]]
    out = []
    for i in range(n):
        e = data[ts[4]+i*entsize:ts[4]+(i+1)*entsize]
        name_off, info, other, shndx, value, size = struct.unpack_from(E+"IBBHQQ", e, 0)
        nm = strtab[name_off:strtab.find(b"\0", name_off)].decode("ascii", "replace")
        out.append((value, nm, size, info, shndx))
    return out

syms = read_symtab(".symtab", ".strtab")
dyms = read_symtab(".dynsym", ".dynstr")

def symname(addr):
    for value, nm, size, info, shndx in syms + dyms:
        if value == addr and nm:
            return nm
    return None

# PLT/GOT 反向映射：addr -> 符号名
def build_reloc_name_map():
    m = {}
    for rt in (".rela.plt", ".rela.dyn"):
        if rt not in sec:
            continue
        r = sec[rt]
        # Elf64_Rela: r_offset(8) r_info(8) r_addend(8)
        n = r[5] // 24
        for i in range(n):
            off = r[4] + i*24
            r_offset, r_info, r_addend = struct.unpack_from(E+"QQQ", data, off)
            typ = r_info & 0xffffffff
            symidx = r_info >> 32
            if typ == 1026 or typ == 1027:  # R_AARCH64_JUMP_SLOT / GLOB_DAT
                nm = None
                for value, name, size, info, shndx in dyms:
                    pass
    # 简单方式：逐个 GOT 槽 -> dynsym
    return m

def got_slot_sym(dynstr, dynsym):
    pass

# 解析 PLT 目标：给定 bl 目标地址，若落在 .plt 则跟到最终 GOT 槽
got = sec.get(".got"); gotplt = sec.get(".got.plt")
relplt = sec.get(".rela.plt")
relplt_map = {}
if relplt is not None:
    n = relplt[5] // 24
    for i in range(n):
        off = relplt[4] + i*24
        r_offset, r_info, r_addend = struct.unpack_from(E+"QQQ", data, off)
        symidx = r_info >> 32
        if symidx < len(dyms):
            v, nm, sz, info, shndx = dyms[symidx]
            relplt_map[r_offset] = nm

def resolve_plt(addr):
    """addr 是 bl 目标；若在 .plt，尝试解 GOT 槽符号。
    简化：AArch64 PLT 条目通常 [adrp x16, page; ldr x17,[x16,off]; add x16,x16,off; br x17]，
    但直接扫描 .plt 会耦合；这里改为：凡 bl 目标命中 .plt 区域，查找 relplt_map 中
    GOT 地址落入的目标。由于难以精确解 PLT，这里列出来自 .rela.plt 的全部符号，
    并打印 bl 目标是否在 .plt 段。"""
    plt = sec.get(".plt")
    if plt is not None and plt[3] <= addr < plt[3] + plt[5]:
        return "<PLT>"
    return None

text = sec[".text"]
code = data[text[4]:text[4]+text[5]]
tbase = text[3]

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True

HALS = [
    (0x490b50, 0x60, "engine_hal_send_data"),
    (0x490d10, 0x60, "engine_hal_receive_data"),
    (0x490fa8, 0x100, "engine_hal_dev_com_init"),
    (0x491024, 0x40, "engine_hal_dev_com_close"),
    (0x4910cc, 0x60, "engine_hal_dev_gpio_init"),
    (0x4911a4, 0x60, "engine_hal_set_gpio_value"),
    (0x491320, 0x60, "engine_hal_get_gpio_value"),
]
plt = sec.get(".plt")

# 汇总所有被 bl 的地址 -> 符号（含 PLT 外部符号粗解：.rela.plt 中符号顺序对应 PLT 槽顺序）
# AArch64 PLT: 每个导入符号一个 16 字节槽，槽 N 对应 .rela.plt 条目 N
plt_slots = {}
if plt is not None and relplt is not None:
    slot_size = 16
    first_slot = plt[3] + 16  # ELF 首个 PLT 槽可能在 +16 之后（保留 16 字节头）
    # 找 .plt 中真正的槽起点：AArch64 通常 .plt 16 字节头 + N*16 槽
    cnt = len(relplt_map)
    for i, (gotoff, nm) in enumerate(relplt_map.items()):
        plt_slots[first_slot + i*slot_size] = nm

for va, size, label in HALS:
    print(f"\n==== {label} @ 0x{va:x} (0x{size:x}) ====")
    start = va - tbase
    for ins in md.disasm(code[start:start+size], va):
        extra = ""
        if ins.mnemonic in ("bl", "b"):
            tgt = ins.address + 4 + int(ins.op_str.lstrip("#"), 16)
            nm = symname(tgt)
            if nm:
                extra = f"  -> {nm}"
            else:
                if plt and plt[3] <= tgt < plt[3]+plt[5]:
                    # 尝试按槽偏移查符号
                    slot = tgt
                    nm2 = plt_slots.get(slot)
                    extra = f"  -> PLT" + (f" {nm2}" if nm2 else "")
                else:
                    extra = f"  -> (内部 0x{tgt:x})"
        elif ins.mnemonic == "adrp":
            pass
        print(f"  0x{ins.address:x}: {ins.mnemonic:8s} {ins.op_str}{extra}")

print("\n== .rela.plt 全部导入符号 (GOT槽 -> 符号) ==")
import collections
sym_to_plt = collections.defaultdict(list)
for i, (gotoff, nm) in enumerate(relplt_map.items()):
    sym_to_plt[nm].append((gotoff, first_slot + i*16))
for nm, lst in sorted(sym_to_plt.items()):
    gotl = ", ".join(f"0x{g:x}" for g, _ in lst)
    print(f"  {nm}: got=({gotl})")

# 打印外部库 EXTERN 符号中与 hal/ipm/usb/pci 相关者（.dynsym 中 shndx=0 的 UND）
print("\n== .dynsym UND 符号（外部导入）中 hal/ipm/usb/pci/gpio 相关 ==")
for value, nm, size, info, shndx in dyms:
    if shndx == 0 and any(k in nm for k in ("hal", "ipm", "usb", "pci", "gpio", "engfw", "eng_", "com_")):
        print(f"  {nm}")