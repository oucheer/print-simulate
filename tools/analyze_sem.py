# -*- coding: utf-8 -*-
"""分析 libosal.so 的 pi_sem* 符号与信号量结构（round 65 需要精确唤醒）"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\lib\libosal.so"
data = open(PATH, "rb").read()
assert data[:4] == b"\x7fELF"
is64 = data[4] == 2
endian = "<" if data[5] == 1 else ">"
print("ELF64:", is64, "endian:", endian)

# section headers
e_shoff = struct.unpack_from(endian + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + "H", data, 0x3E)[0]

def get_section(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(endian + "IIQQQQIIQQ", data, off)

sections = [get_section(i) for i in range(e_shnum)]
# sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_addralign, sh_entsize
shstr = sections[e_shstrndx]
shstr_data = data[shstr[4]:shstr[4] + shstr[5]]

def sec_name(i):
    n = sections[i][0]
    end = shstr_data.index(b"\0", n)
    return shstr_data[n:end].decode()

sec_by_name = {sec_name(i): sections[i] for i in range(e_shnum)}

symtab = sec_by_name.get(".symtab")
strtab = sec_by_name.get(".strtab")

def read_strtab(strtab_sec, off):
    d = data[strtab_sec[4]:strtab_sec[4] + strtab_sec[5]]
    end = d.index(b"\0", off)
    return d[off:end].decode(errors="replace")

symbols = {}
if symtab:
    entsize = symtab[9] or 24
    for i in range(symtab[5] // entsize):
        st = struct.unpack_from(endian + "IBBHQQ", data, symtab[4] + i * entsize)
        name = read_strtab(strtab, st[0])
        st_info, st_shndx, st_value, st_size = st[1], st[3], st[4], st[5]
        if st_value:
            symbols[name] = (st_value, st_size, st_shndx)

print("== pi_sem / pol sem symbols ==")
for name in sorted(symbols):
    if "sem" in name.lower() or "sema" in name.lower():
        v, sz, sh = symbols[name]
        print(f"  0x{v:08x} sz={sz} {name}")

# 定位可执行段 .text
text = sec_by_name.get(".text")
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False

def disasm_range(addr, size):
    base_off = text[4] + (addr - text[3])
    code = data[base_off:base_off + size]
    out = []
    for ins in md.disasm(code, addr):
        out.append(f"  0x{ins.address:x}: {ins.mnemonic:<8} {ins.op_str}")
    return out

# 反汇编 binder 相关
for name in ["binder_call", "binder_start", "binder_done", "binder_open",
             "binder_write", "binder_parse", "binder_send_reply", "binder_thr",
             "binder_add_target", "binder_stop"]:
    if name in symbols:
        v, sz, sh = symbols[name]
        print(f"\n==== {name} @ 0x{v:x} sz={sz} ====")
        for line in disasm_range(v, sz):
            print(line)
