# -*- coding: utf-8 -*-
"""Step 4: 反汇编 public_if_act_* 包装器（查表分发入口）+ engine_process_mgr_print_sequence_*（打印序列状态机），
并找 public_if_act_* 的 bl 调用者。
"""
import struct, sys
sys.stdout = open(r"runtime/act_dispatch.txt", "w", encoding="utf-8", errors="replace")
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PATH = r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx"
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
text = by[".text"]
tblk = data[text[4]:text[4] + text[5]]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

def v2o(v):
    for s in secs:
        if s[3] <= v < s[3] + s[5] and s[4]:
            return s[4] + (v - s[3])
    return None

def dis(addr, size, label):
    print("\n==== %s @ 0x%x (0x%x 字节) ====" % (label, addr, size))
    off = v2o(addr)
    if off is None:
        print("  无法定位")
        return
    for ins in md.disasm(data[off:off + size], addr):
        print("  0x%x: %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))

# 1) public_if_act_* 包装器（查表分发入口）
WRAPPERS = [
    (0x494604, 0x180, "engine_general_if_layer_public_if_act_init_step"),
    (0x494808, 0x200, "engine_general_if_layer_public_if_act_warmup_step"),
    (0x494a10, 0x200, "engine_general_if_layer_public_if_act_reinit_step"),
    (0x494cbc, 0x140, "engine_general_if_layer_public_if_act_prepare_print"),
    (0x4952ec, 0x140, "engine_general_if_layer_public_if_act_print_execute"),
    (0x494c14, 0x90,  "engine_general_if_layer_public_if_act_handshake"),
    (0x496c84, 0x90,  "engine_general_if_layer_public_if_act_finisher"),
]
for a, s, n in WRAPPERS:
    dis(a, s, n)

# 2) 找 public_if_act_* 的 bl 调用者
print("\n\n== bl 调用者 ==")
targets = {a: n for a, s, n in WRAPPERS}
callers = {}
for i in range(0, len(tblk) - 4, 4):
    ins = next(md.disasm(tblk[i:i + 4], text[3] + i))
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str, 16)
        except Exception:
            continue
        if tgt in targets:
            callers.setdefault(tgt, set()).add(text[3] + i)
for t, name in targets.items():
    c = callers.get(t, set())
    print("\n  %s (0x%x) : %d 个调用者" % (name, t, len(c)))
    for ca in sorted(c):
        print("    0x%x" % ca)

# 3) print_sequence 状态机关键函数（引擎打印序列）
print("\n\n== print_sequence 状态机 ==")
SEQ = [
    (0x4772ec, 0x60, "print_sequence_prepare_print"),
    (0x477354, 0x200, "print_sequence_first_start_print"),
    (0x477524, 0x250, "print_sequence_print"),
    (0x477974, 0x80, "print_sequence_print_without_tod"),
    (0x477e40, 0x50, "print_sequence_print_video_ready"),
    (0x477e90, 0x60, "print_sequence_print_paper_exited"),
    (0x477f50, 0x50, "print_sequence_print_done"),
    (0x477ff4, 0x80, "print_sequence_print_execute_done"),
    (0x47858c, 0x70, "print_sequence_print_cancel"),
    (0x4785ec, 0x70, "print_sequence_print_pause"),
]
for a, s, n in SEQ:
    dis(a, s, n)
