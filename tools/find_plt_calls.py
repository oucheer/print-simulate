# -*- coding: utf-8 -*-
"""mfp.afx：定位 bind/listen/socket/accept/connect 的 PLT 调用点"""
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

# 1) .rela.plt -> 符号名 -> GOT 地址
rela = by.get(".rela.plt")
dynsym = by[".dynsym"]; dynstr = by[".dynstr"]
entsize = dynsym[9] or 24
sym_names = []
for i in range(dynsym[5] // entsize):
    e = struct.unpack_from(endian + "IBBHQQ", data, dynsym[4] + i * entsize)
    sym_names.append(rs(dynstr, e[0]))

got_plt_syms = {}  # got_addr -> symname
if rela:
    es = rela[9] or 24
    for i in range(rela[5] // es):
        e = struct.unpack_from(endian + "QQq", data, rela[4] + i * es)
        r_offset, r_info = e[0], e[1]
        sym_idx = r_info >> 32
        if sym_idx < len(sym_names):
            got_plt_syms[r_offset] = sym_names[sym_idx]

# 2) .plt 反汇编：每个 plt 桩入口 -> 对应符号（按 rela 顺序）
plt_sec = by.get(".plt")
got_plt = by.get(".got.plt")
plt_start = plt_sec[3]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
code = data[plt_sec[4]:plt_sec[4] + plt_sec[5]]
plt_entries = []  # (entry_addr, symname)
i = 0
# 第一个 PLT 桩是 resolver（16字节头 + 后续），通常 entry 0 = 32 偏移起是函数桩
first = True
for ins in md.disasm(code, plt_start):
    pass
# 更稳的方式：got 顺序对应 plt 槽（entry 偏移 = 32 + n*16）
got_addrs = sorted(got_plt_syms.keys())
for n, ga in enumerate(got_addrs):
    entry = plt_start + 32 + n * 16
    plt_entries.append((entry, got_plt_syms[ga]))

print("== PLT 目标（bind/listen/socket 等）==")
targets = {}
for addr, nm in plt_entries:
    if nm in ("bind", "listen", "socket", "accept", "connect", "recv", "setsockopt", "getsockopt", "getsockname", "send", "sendto", "recvfrom", "shutdown", "poll", "select", "epoll_create", "epoll_ctl", "epoll_wait", "socketpair"):
        targets[addr] = nm
        print(f"  plt 0x{addr:x} -> {nm}")

# 3) 扫描 .text 找 bl 到这些 plt 目标
text = by[".text"]
code = data[text[4]:text[4] + text[5]]
calls = []  # (call_site, sym)
for ins in md.disasm(code, text[3]):
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str.strip("#"), 0)
        except Exception:
            continue
        if tgt in targets:
            calls.append((ins.address, targets[tgt]))

# 按函数分组（粗略：找相邻 call 的聚集）
print("\n== bind/listen/socket 调用点 ==")
for addr, nm in calls:
    print(f"  0x{addr:x}  bl {nm}")

# 对每个调用点，打印所在函数上下文（向前找最近函数边界不可行，直接打印周围 40 条）
print("\n== 每个调用点上下文（前 12 条指令）==")
insns = list(md.disasm(code, text[3]))
addr2idx = {ins.address: i for i, ins in enumerate(insns)}
for addr, nm in calls:
    if nm not in ("bind", "listen", "socket", "accept", "connect"):
        continue
    idx = addr2idx.get(addr)
    print(f"\n--- 0x{addr:x} bl {nm} ---")
    for j in range(max(0, idx - 12), min(len(insns), idx + 1)):
        p = insns[j]
        print(f"  0x{p.address:x}: {p.mnemonic:<8} {p.op_str}")
