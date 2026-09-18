#!/usr/bin/env python3
"""disasm_range.py — 按虚拟地址范围反汇编 AArch64 ELF 代码段（capstone）

用法:
  python tools/disasm_range.py <elf> <start_hex> <end_hex> [--bytes]
    --bytes  每条指令附带原始字节
"""
import struct
import sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN


def load_va(path, start, size):
    data = open(path, "rb").read()
    e_phoff, = struct.unpack_from("<Q", data, 0x20)
    e_phentsize, = struct.unpack_from("<H", data, 0x36)
    e_phnum, = struct.unpack_from("<H", data, 0x38)
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, = struct.unpack_from("<I", data, o)
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<QQQQQ", data, o + 8)
        if p_type == 1 and p_vaddr <= start < p_vaddr + p_filesz:
            off = p_offset + (start - p_vaddr)
            return data[off:off + size]
    return None


def main():
    path = sys.argv[1]
    start = int(sys.argv[2], 16)
    end = int(sys.argv[3], 16)
    show_bytes = "--bytes" in sys.argv
    code = load_va(path, start, end - start)
    if code is None:
        print("VA 0x%x not mapped" % start)
        return 1
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    for insn in md.disasm(code, start):
        if show_bytes:
            print("0x%x:  %-24s %s %s" % (insn.address, insn.bytes.hex(), insn.mnemonic, insn.op_str))
        else:
            print("0x%x:  %s %s" % (insn.address, insn.mnemonic, insn.op_str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
