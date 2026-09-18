# -*- coding: utf-8 -*-
"""反汇编 mfp.afx 关键函数：0x5fa168(lpd_listen前置检查)、lpd_thread 尾部循环"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
data = open(PATH, "rb").read()
endian = "<" if data[5] == 1 else ">"
e_shoff = struct.unpack_from(endian + "Q", data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + "H", data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + "H", data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + "H", data, 0x3E)[0]

def get_sec(i):
    off = e_shoff + i * e_shentsize
    return struct.unpack_from(endian + "IIQQQQIIQQ", data, off)

secs = [get_sec(i) for i in range(e_shnum)]
shstr = secs[e_shstrndx]
shstr_data = data[shstr[4]:shstr[4] + shstr[5]]
def sec_name(i):
    n = secs[i][0]
    e = shstr_data.index(b"\0", n)
    return shstr_data[n:e].decode()
by = {sec_name(i): secs[i] for i in range(e_shnum)}
text = by[".text"]
print(".text vaddr=0x%x off=0x%x sz=0x%x" % (text[3], text[4], text[5]))

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

def disasm(addr, size, label=""):
    off = text[4] + (addr - text[3])
    code = data[off:off + size]
    print(f"\n==== {label} @ 0x{addr:x} sz={size} ====")
    for ins in md.disasm(code, addr):
        print(f"  0x{ins.address:x}: {ins.mnemonic:<9} {ins.op_str}")

# 1) lpd_listen_create 的前置检查 0x5fa168
disasm(0x5fa168, 0x120, "lpd_listen_precheck")

# 2) lpd_thread 尾部循环（0x683e08 之前的部分）：0x683a30 - 0x683e08
disasm(0x683a30, 0x3e08 - 0x3a30, "lpd_thread_loop_tail")

# 3) 完整监听链函数（socket+bind+listen+accept @ 0x74c5c0-0x74c8e0）
disasm(0x74c5c0, 0x320, "listen_service_74c6")

# 4) bind+listen 对 @ 0x66af00-0x66b420
disasm(0x66b000, 0x420, "bind_listen_66b0")

# 5) LPD 监听线程创建点 @ 0x74f000-0x74f7e0
disasm(0x74ef00, 0x2e0, "lpd_svc_init_74ef")
