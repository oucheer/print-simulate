#!/usr/bin/env python3
"""find_calls.py — 用 capstone 在指定地址范围内查找 bl 调用目标（AArch64）

用法:
  python tools/find_calls.py <elf> <start_hex> <size_hex> [--targets 5fdac8,5fdac8]
输出: 每条 bl 的地址、目标；--targets 时只列出命中目标的调用点。
"""
import sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

def load_text(path, start, size):
    """按虚拟地址读取：解析 ELF program headers，找到包含该 VA 的 PT_LOAD"""
    import struct
    data = open(path, "rb").read()
    e_phoff, = struct.unpack_from("<Q", data, 0x20)
    e_phentsize, = struct.unpack_from("<H", data, 0x36)
    e_phnum, = struct.unpack_from("<H", data, 0x38)
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from("<II", data, o)
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<QQQQQ", data, o + 8)
        if p_type == 1 and p_vaddr <= start < p_vaddr + p_filesz:
            off = p_offset + (start - p_vaddr)
            return data[off:off + size]
    return None

def main():
    path = sys.argv[1]
    start = int(sys.argv[2], 16)
    size = int(sys.argv[3], 16)
    targets = set()
    if "--targets" in sys.argv:
        for t in sys.argv[sys.argv.index("--targets") + 1].split(","):
            targets.add(int(t, 16))
    code = load_text(path, start, size)
    if code is None:
        print("VA 0x%x not in any PT_LOAD" % start); return 1
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    n = 0
    for insn in md.disasm(code, start):
        if insn.mnemonic == "bl":
            tgt = int(insn.op_str.lstrip("#"), 16) if insn.op_str.startswith("#") else None
            if targets:
                if tgt in targets:
                    print("bl 0x%x -> 0x%x" % (insn.address, tgt)); n += 1
            else:
                print("0x%x: %s %s" % (insn.address, insn.mnemonic, insn.op_str)); n += 1
    print("total", n)
    return 0

if __name__ == "__main__":
    sys.exit(main())
