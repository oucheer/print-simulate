# -*- coding: utf-8 -*-
"""Step 4: 搜真实引擎 API（act_init/act_warmup/prepare_print/set_*）的 bl 调用者。
目标：找到打印任务如何驱动引擎接口（print task -> 0x51c -> engine API -> HAL）。
"""
import struct, sys
sys.stdout = open(r"runtime/api_callers.txt", "w", encoding="utf-8", errors="replace")
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

# 目标 API（来自 s_engframework_api_array 映射 + 符号名）
TARGETS = {
    0x505f38: "act_init_step1",
    0x505fc0: "act_init_step2",
    0x5060d0: "act_init_step3",
    0x5062d0: "act_init_step4",
    0x5064dc: "act_init_step5",
    0x506e88: "act_init_step6",
    0x506fbc: "act_warmup_step1",
    0x5071b4: "act_warmup_step2",
    0x5072c4: "act_warmup_step3",
    0x5074c4: "act_warmup_step4",
    0x5076d0: "act_warmup_step5",
    0x5080bc: "act_warmup_step6",
    0x5081dc: "act_reinit_step1",
    0x508328: "act_reinit_step2",
    0x50844c: "act_reinit_step3",
    0x508660: "act_reinit_step4",
    0x508880: "act_reinit_step5",
    0x509240: "act_reinit_step6",
    0x509360: "prepare_print",
    0x50939c: "set_paper_type",
    0x509774: "set_paper_size",
    0x5098ec: "set_print_mode",
    0x509ad4: "print_execute",  # 摘要提到的打印执行
}

# 1) 全 .text bl 扫描，统计每个目标的调用者
print("== 1) 引擎 API 的 bl 调用者 ==")
callers = {}  # target -> set(caller_addr)
for i in range(0, len(tblk) - 4, 4):
    ins = next(md.disasm(tblk[i:i + 4], text[3] + i))
    if ins.mnemonic == "bl":
        try:
            tgt = int(ins.op_str, 16)
        except Exception:
            continue
        if tgt in TARGETS:
            callers.setdefault(tgt, set()).add(text[3] + i)

for t, name in TARGETS.items():
    c = callers.get(t, set())
    print("\n  %s (0x%x) : %d 个调用者" % (name, t, len(c)))
    for ca in sorted(c):
        print("    0x%x" % ca)

# 2) 调用者中按"调用最密集的函数"聚类：找出哪些函数同时调用多个 act_* API
print("\n== 2) 调用多个引擎 API 的汇聚函数（likely state machine 驱动） ==")
from collections import defaultdict
func_of = {}  # caller -> set(names)
for t, cs in callers.items():
    for ca in cs:
        func_of.setdefault(ca, set()).add(TARGETS[t])
for ca, names in sorted(func_of.items(), key=lambda kv: -len(kv[1])):
    print("  0x%x 调用: %s" % (ca, ", ".join(sorted(names))))

# 3) 对调用者反汇编（按函数 prologue 聚类，打印每个调用者周围 12 条指令）
print("\n== 3) 调用者上下文反汇编 ==")
def v2o(v):
    for s in secs:
        if s[3] <= v < s[3] + s[5] and s[4]:
            return s[4] + (v - s[3])
    return None

done = set()
for ca in sorted(func_of):
    off = v2o(ca - 0x20)
    if off is None or ca in done:
        continue
    done.add(ca)
    print("\n--- 0x%x (调用 %s) ---" % (ca, ", ".join(sorted(func_of[ca]))))
    for ins in md.disasm(data[off:off + 0x60], ca - 0x20):
        mark = " <== BL API" if ins.address == ca else ""
        print("  0x%x: %-8s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
