# -*- coding: utf-8 -*-
"""Step 4: 定位 pi_engfw_* 日志字符串的引用者与引擎接口真实调用点
1) 扫描所有可读段，找 8B/4B 数据指针 == 引擎日志串地址（可能为日志表）
2) 扫 .text：adrp+add / adrp+ldr / ldr literal 三种模式引用这些串
3) 反汇编关键引擎函数：0x505b44 (engine_general_if_layer_notice_engfw_print_status)
"""
import struct, sys
sys.stdout = open(r"runtime\engfw_xref_full.txt", "w", encoding="utf-8", errors="replace")
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

def v2o(vaddr):
    for s in secs:
        if s[3] <= vaddr < s[3] + s[5] and s[4]:
            return s[4] + (vaddr - s[3])
    return None

def sec_of(vaddr):
    for s in secs:
        if s[3] <= vaddr < s[3] + s[5]:
            return sn(secs.index(s)) if secs.index(s) < e_shnum else "?"
    return None

# 目标字符串（PART B 输出）
targets = [
0x771367,0x77225f,0x77228f,0x772e27,0x772f7f,0x772fcf,0x77344f,0x77419f,
0x7741d7,0x774207,0x77423f,0x77426f,0x7742a7,0x7742df,0x774317,0x77434f,
0x77438f,0x7743c7,0x7743f7,0x774427,0x77451f,0x774737,0x7747ff,0x774857,
0x7748af,0x7748d7,0x774919,0x774949,0x774dff,0x774e37,0x776387,0x776475,
0x777ddf,0x778347,
]
tset = set(targets)
pages = sorted({(t & ~0xFFF) for t in targets})

print("== 1) 数据指针表（8B 小端）指向目标串 ==")
for s in secs:
    nm = sn(secs.index(s))
    if nm in (".text", ".comment", ".shstrtab", ".symtab", ".strtab", ".rela.plt", ".rela.dyn", ".plt", ".got", ".got.plt", ".dynsym", ".dynstr", ".eh_frame", ".hash", ".gnu.hash", ".note.gnu.property"):
        continue
    if s[3] == 0 or s[5] == 0:
        continue
    blk = data[s[4]:s[4] + s[5]]
    found = []
    for t in targets:
        i = 0
        while True:
            i = blk.find(struct.pack("<Q", t), i)
            if i < 0:
                break
            found.append((s[3] + i, t))
            i += 1
    if found:
        print("  section %s: %d 个指针" % (nm, len(found)))
        for va, t in found[:30]:
            print("    0x%x -> 0x%x" % (va, t))

print()
print("== 2) .text adrp+add / adrp+ldr / ldr-literal 引用目标串页面 ==")
text = by[".text"]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
code = data[text[4]:text[4] + text[5]]
insns = list(md.disasm(code, text[3]))

hits = []
for i, ins in enumerate(insns):
    if ins.mnemonic == "adrp":
        if ins.address < 0:
            continue
        # adrp 目标页面
        try:
            pg = int(ins.op_str.split("#")[1], 0)
        except Exception:
            continue
        if pg not in pages:
            continue
        # 向后最多 8 条找 add/ldr 使用同寄存器
        reg = ins.op_str.split(",")[0].strip()
        for j in range(i + 1, min(i + 9, len(insns))):
            nxt = insns[j]
            ops = nxt.op_str.split(",")
            if len(ops) >= 2 and ops[1].strip() == reg:
                if nxt.mnemonic in ("add", "adds"):
                    try:
                        off = int(ops[2].split("#")[1], 0)
                    except Exception:
                        continue
                    val = pg + off
                    if val in tset:
                        hits.append((ins.address, val, "adrp+add"))
                elif nxt.mnemonic == "ldr":
                    # adrp+ldr x0,[x0,#off] 少见；跳过
                    pass
                break
for h in sorted(hits):
    print("  0x%x  -> 0x%x  (%s)" % h)
print("  total: %d" % len(hits))

print()
print("== 3) 反汇编引擎通知函数 0x505b44 ==")
addr = 0x505b44
off = v2o(addr)
if off:
    for ins in md.disasm(data[off:off + 0x200], addr):
        print("  0x%x: %s %s" % (ins.address, ins.mnemonic, ins.op_str))
else:
    print("  vaddr 不在映射内")

print()
print("== 4) 符号表定位 0x505b44 / 0x68eb18 周围全部引擎相关 static 符号 ==")
if ".symtab" in by and ".strtab" in by:
    symsec = by[".symtab"]; strsec = by[".strtab"]
    entsize = symsec[9] or 24
    for i in range(symsec[5] // entsize):
        e = struct.unpack_from(endian + "IBBHQQ", data, symsec[4] + i * entsize)
        if e[0] >= strsec[5]:
            continue
        nm = data[strsec[4] + e[0]:].split(b"\0")[0].decode(errors="replace")
        if "eng" in nm.lower() or "engine" in nm.lower() or "print_status" in nm.lower():
            print("  0x%x  %s" % (e[4], nm))