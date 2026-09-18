# -*- coding: utf-8 -*-
"""mfp.afx：导入的 net syscall 符号 + .text 中直接 svc socket/bind/listen 的位置"""
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
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

print("== UNDEF 导入（net 相关）==")
dyn = by[".dynsym"]; dynstr = by[".dynstr"]
entsize = dyn[9] or 24
import re
wanted = re.compile(r"^(socket|bind|listen|accept|connect|getpeername|getsockname|getsockopt|setsockopt|sendto|recvfrom|sendmsg|recvmsg|send|recv|shutdown)$|^__sendto$|^__recvfrom$")
for i in range(dyn[5] // entsize):
    e = struct.unpack_from(endian + "IBBHQQ", data, dyn[4] + i * entsize)
    st_shndx = e[3]
    if st_shndx != 0:
        continue
    nm = rs(dynstr, e[0])
    if wanted.search(nm):
        print(f"  import {nm}")

print("\n== .text 直接 svc 调用（socket/bind/listen 等）==")
text = by[".text"]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
code = data[text[4]:text[4] + text[5]]
found = []
insns = list(md.disasm(code, text[3]))
for idx in range(len(insns)):
    ins = insns[idx]
    if ins.mnemonic == "svc":
        # 向前找最近的 mov x8, #N
        nr = None
        for j in range(idx - 1, max(-1, idx - 8), -1):
            p = insns[j]
            if p.mnemonic == "mov" and p.op_str.startswith("x8, #"):
                try:
                    nr = int(p.op_str.split("#")[1], 0)
                except Exception:
                    nr = None
                break
            if p.mnemonic == "movk" and "x8" in p.op_str:
                break
        if nr is not None:
            found.append((ins.address, nr))
for addr, nr in found:
    if nr in (198, 199, 200, 201, 202, 203, 204, 205, 206, 53, 9, 7, 5, 6):
        print(f"  svc@{addr:#x} syscall={nr}")
