# -*- coding: utf-8 -*-
"""Step 4 深挖:
1) 反汇编 engine_hal_interface_send / engine_hal_send_data / engine_hal_pend / engine_hal_dev_com_init
2) 转储 s_engframework_api_array (0x8b06f0) 前 N 项
3) 转储 s_Engine_If_Hardware (0xa75880)
4) 反汇编 engine_general_if_layer_frame_unpack（帧解析）
5) 搜索字符串指针表指向 0x77xxxx 的 4B 偏移表/8B 表（日志表再查）
"""
import struct, sys
sys.stdout = open(r"runtime/engine_deep.txt", "w", encoding="utf-8", errors="replace")
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
def sec_of(v):
    for n, s in by.items():
        if s[3] <= v < s[3] + s[5] and s[4]:
            return n
    return None
def v2o(v):
    for s in secs:
        if s[3] <= v < s[3] + s[5] and s[4]:
            return s[4] + (v - s[3])
    return None

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
def dis(addr, size, label=""):
    off = v2o(addr)
    if off is None:
        print("  (0x%x not mapped)" % addr)
        return
    print("\n==== %s @ 0x%x sz=0x%x (%s) ====" % (label, addr, size, sec_of(addr)))
    for ins in md.disasm(data[off:off + size], addr):
        print("  0x%x: %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))

def dump_u64(addr, n, label=""):
    off = v2o(addr)
    if off is None:
        print("  (0x%x not mapped)" % addr); return
    print("\n==== %s @ 0x%x (%s) ====" % (label, addr, sec_of(addr)))
    for i in range(n):
        v = struct.unpack_from("<Q", data, off + i * 8)[0]
        tag = ""
        if sec_of(v):
            tag = "<- %s" % sec_of(v)
        print("  [%2d] 0x%x : 0x%x %s" % (i, addr + i * 8, v, tag))

# 1) engine_process_layer_send / receive 层
dis(0x491dec, 0x110, "engine_process_layer_send_cmd_send")
print("\n")
dis(0x491500, 0x160, "engine_process_layer_receive_parse_frame")
print("\n")
dis(0x490948, 0x130, "engine_hal_interface_send")
print("\n")
dis(0x490b50, 0x130, "engine_hal_send_data")
print("\n")
dis(0x490c74, 0x100, "engine_hal_pend")
print("\n")
dis(0x490fa8, 0x130, "engine_hal_dev_com_init")

# 2) API 数组表
dump_u64(0x8b06f0, 32, "s_engframework_api_array")

# 3) 硬件接口结构
dump_u64(0xa75880, 16, "s_Engine_If_Hardware")

# 4) 帧解析
dis(0x50bc38, 0x90, "engine_general_if_layer_frame_unpack")

# 5) 日志串引用再查：4B 偏移表 + 全段精确搜索 0x77 前缀页引用
print("\n\n==== 5) 0x77xxxx 日志串引用再查（4B/8B 数据/代码页） ====")
tgt = [0x771367, 0x77225f, 0x77419f, 0x774737, 0x7748af, 0x776387, 0x776475]
for secn in (".data", ".data.rel.ro", ".rodata", ".got", ".got.plt"):
    if secn not in by:
        continue
    s = by[secn]
    blk = data[s[4]:s[4] + s[5]]
    found8 = []
    for t in tgt:
        i = 0
        while True:
            i = blk.find(struct.pack("<Q", t), i)
            if i < 0: break
            found8.append((s[3] + i, t)); i += 1
    if found8:
        print("  %s 8B指针: %d" % (secn, len(found8)))
        for fa, t in found8[:20]:
            print("    0x%x -> 0x%x" % (fa, t))

# 页面引用扫描：mmp handler 所在 .text 的反汇编中若有 adrp #0x77xxxx -> 记录
print("\n  .text 中 adrp page=0x77.. 的引用计数统计:")
from collections import Counter
pgcount = Counter()
for ins in md.disasm(data[by[".text"][4]:by[".text"][4] + by[".text"][5]], by[".text"][3]):
    if ins.mnemonic == "adrp":
        try:
            p = int(ins.op_str.split("#")[1], 0)
            if (p & 0xFF0000) == 0x770000:
                pgcount[p] += 1
        except Exception:
            pass
for p, c in sorted(pgcount.items()):
    print("  adrp #0x%x : %d 次" % (p, c))