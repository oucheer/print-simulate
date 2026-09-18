#!/usr/bin/env python3
"""make_binder_stub.py — 生成 binder_stub.so（LD_PRELOAD 拦截 /dev/binder）

方法：keystone 汇编 aarch64 机器码 + 手工构造 ELF64 shared object（ET_DYN）。
- 每个导出函数前插入 nop nop 标记，capstone 反汇编定位函数入口地址
- 纯 syscall 实现，无 libc 依赖，可被 glibc 进程加载
- 导出：openat, open, ioctl, mmap, close, fcntl, poll
"""
import struct
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN
import capstone

OUT = r"tools\binder_stub.so"

MARK = "    nop\n    nop\n"  # 函数入口标记（两个 nop）

# ---------------- 各函数汇编（跨引用用内部标签，单块一次汇编） ----------------
FUNCS = [
    ("path_is_binder", """
path_is_binder:
    adr x1, str_binder
ploop:
    ldrb w2, [x1], #1
    ldrb w3, [x0], #1
    cbz w2, pfound
    cmp w3, w2
    b.ne pnomatch
    b ploop
pfound:
    mov x0, #1
    ret
pnomatch:
    mov x0, #0
    ret
"""),
    ("openat", """
openat:
    stp x29, x30, [sp, #-16]!
    stp x19, x20, [sp, #-16]!
    stp x21, x22, [sp, #-16]!
    mov x29, sp
    mov x19, x0
    mov x20, x1
    mov x21, x2
    mov x0, x20
    bl path_is_binder
    cbz x0, openat_real
    mov x0, #0x777
openat_ret:
    ldp x21, x22, [sp], #16
    ldp x19, x20, [sp], #16
    ldp x29, x30, [sp], #16
    ret
openat_real:
    mov x0, x19
    mov x1, x20
    mov x2, x21
    mov x3, #0
    mov x4, #0
    mov x5, #0
    mov x6, #0
    mov x8, #56
    svc #0
    b openat_ret
"""),
    ("open", """
open:
    mov x2, x0
    mov x3, x1
    mov x0, #-100
    mov x1, x2
    mov x2, x3
    b openat
"""),
    ("ioctl", """
ioctl:
    cmp x0, #0x777
    b.ne ioctl_real
    mov x3, #0x6203
    movk x3, #0xC004, lsl #16
    cmp x1, x3
    b.ne ioctl_fake
    mov w4, #8
    str w4, [x2]
ioctl_fake:
    mov x0, #0
    ret
ioctl_real:
    mov x8, #29
    svc #0
    ret
"""),
    ("mmap", """
mmap:
    cmp x4, #0x777
    b.ne mmap_real
    orr x3, x3, #0x20
    mov x4, #-1
mmap_real:
    mov x8, #222
    svc #0
    ret
"""),
    ("close", """
close:
    cmp x0, #0x777
    b.ne close_real
    mov x0, #0
    ret
close_real:
    mov x8, #57
    svc #0
    ret
"""),
    ("fcntl", """
fcntl:
    cmp x0, #0x777
    b.ne fcntl_real
    mov x0, #0
    ret
fcntl_real:
    mov x8, #25
    svc #0
    ret
"""),
    ("poll", """
poll:
    cmp x1, #0
    b.eq poll_real
    mov x9, x0
    mov x10, x1
    mov x11, #0
    mov x12, #0
poll_loop:
    cmp x11, x10
    b.ge poll_done
    mov x13, x11
    lsl x13, x13, #3
    add x13, x9, x13
    ldr w14, [x13]
    cmp w14, #0x777
    b.ne poll_notfake
    mov w15, #0x1
    strh w15, [x13, #6]
    add x12, x12, #1
    b poll_next
poll_notfake:
    strh wzr, [x13, #6]
poll_next:
    add x11, x11, #1
    b poll_loop
poll_done:
    cbz x12, poll_real
    mov x0, x12
    ret
poll_real:
    mov x8, #7
    svc #0
    ret
"""),
    # pipe/pipe2 拦截：创建后将管道缓冲扩到 1MB，防止固件 plog 洪峰填满 64KB 管道
    # 导致记录线程拿不到信号（慢仿真时序竞态）造成全进程写阻塞死锁。
    ("pipe2", """
pipe2:
    mov x8, #221
    svc #0
    cmp x0, #0
    b.ne pipe2_ret
    ldr w2, [x0]
    ldr w3, [x0, #4]
    mov w0, w2
    mov x1, #1031
    mov x2, #0x100000
    mov x8, #25
    svc #0
    mov w0, w3
    mov x1, #1031
    mov x2, #0x100000
    mov x8, #25
    svc #0
    mov x0, #0
pipe2_ret:
    ret
"""),
    ("pipe", """
pipe:
    mov x1, #0
    b pipe2
"""),
    # bind 拦截：把 IPv4 绑定的 127.0.0.1 改为 0.0.0.0（仿真环境需外部 hostfwd 可达）
    ("bind", """
bind:
    stp x29, x30, [sp, #-16]!
    stp x19, x20, [sp, #-16]!
    stp x21, x22, [sp, #-16]!
    mov x29, sp
    mov x19, x0
    mov x20, x1
    mov x21, x2
    cmp x21, #8
    b.lo bind_real
    ldrh w22, [x20]
    cmp w22, #2
    b.ne bind_real
    str wzr, [x20, #4]
bind_real:
    mov x0, x19
    mov x1, x20
    mov x2, x21
    mov x8, #49
    svc #0
    ldp x21, x22, [sp], #16
    ldp x19, x20, [sp], #16
    ldp x29, x30, [sp], #16
    ret
"""),
    # 服务发现/事务拦截：无真实 service_manager，伪造事件管理器可用。
    ("svcmgr_get_service", """
svcmgr_get_service:
    mov x0, #1
    ret
"""),
    ("binder_call", """
binder_call:
    mov x0, #0
    ret
"""),
    # bio_* 回复解析拦截：binder_call 不填充回复，让解析函数返回"空回复"语义。
    ("bio_get_uint32", """
bio_get_uint32:
    mov x0, #0
    ret
"""),
    ("bio_get_string8", """
bio_get_string8:
    mov x0, #0
    ret
"""),
    ("bio_get_string16", """
bio_get_string16:
    mov x0, #0
    ret
"""),
    ("bio_get_buffer", """
bio_get_buffer:
    mov x0, #0
    ret
"""),
    ("bio_get_fd", """
bio_get_fd:
    mov x0, #-1
    ret
"""),
    ("bio_get_ref", """
bio_get_ref:
    mov x0, #0
    ret
"""),
    ("bio_init_from_txn", """
bio_init_from_txn:
    mov x0, #0
    ret
"""),
]

DATA = """
str_binder:
    .asciz "/dev/binder"
.align 2
"""

EXPORTS = ["openat", "open", "ioctl", "mmap", "close", "fcntl", "poll", "pipe2", "pipe", "bind", "svcmgr_get_service", "binder_call", "bio_get_uint32", "bio_get_string8", "bio_get_string16", "bio_get_buffer", "bio_get_fd", "bio_get_ref", "bio_init_from_txn"]
SONAME = "binder_stub.so"


def elf_hash(name):
    h = 0
    for c in name.encode():
        h = (h << 4) + c
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g
    return h


def assemble():
    asm_src = ""
    for name, body in FUNCS:
        asm_src += MARK + body
    asm_src += DATA
    ks = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    code, _n = ks.asm(asm_src)
    text = bytes(code)
    return text


def locate_funcs(text, base):
    """用 nop nop 标记定位函数入口"""
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    insns = list(md.disasm(text, base))
    entries = []
    prev_nop = False
    for ins in insns:
        if ins.mnemonic == "nop":
            if prev_nop:
                entries.append(ins.address + 4)  # 第二个 nop 之后
            prev_nop = True
        else:
            prev_nop = False
    return entries


def build():
    text_vaddr = 64 + 56 * 2  # ELF header + 2 phdr = 0xB0
    text = assemble()
    # 定位函数入口（第一个标记 = path_is_binder，其后按 FUNCS 顺序）
    entries = locate_funcs(text, text_vaddr)
    func_addr = {}
    names = [n for n, _ in FUNCS]
    for i, addr in enumerate(entries):
        if i < len(names):
            func_addr[names[i]] = addr
    print("func entries:", {k: hex(v) for k, v in func_addr.items()})

    # ---- .dynstr ----
    strtab = b"\0"
    name_offs = {}
    for s in EXPORTS:
        name_offs[s] = len(strtab)
        strtab += s.encode() + b"\0"
    soname_off = len(strtab)
    strtab += SONAME.encode() + b"\0"

    # ---- .dynsym ----
    nsyms = 1 + len(EXPORTS)
    symtab = bytearray(24)  # null symbol
    for i, s in enumerate(EXPORTS):
        st_name = name_offs[s]
        st_info = 0x12  # STB_GLOBAL << 4 | STT_FUNC
        st_other = 0
        st_shndx = 1
        st_value = func_addr[s]
        st_size = 0
        symtab += struct.pack("<IBBHQQ", st_name, st_info, st_other, st_shndx, st_value, st_size)

    # ---- .hash (SysV) ----
    nbucket = 1
    nchain = nsyms
    bucket = [1]          # 全部符号进桶 0
    chain = list(range(1, nsyms)) + [0]  # 1->2->3...->0
    hash_tbl = struct.pack("<II", nbucket, nchain) + struct.pack("<%dI" % len(bucket), *bucket) + struct.pack("<%dI" % len(chain), *chain)

    # ---- .dynamic ----
    # 注意：不可使用 tag 8（DT_RELASZ）——glibc 会因无 DT_RELA 指针而解引用 NULL 崩溃。
    # 符号个数由 DT_HASH 的 nchain 决定，无需 SYMTABSZ。
    dyn_entries = [
        (6, 0),   # DT_SYMTAB
        (5, 0),   # DT_STRTAB
        (4, 0),   # DT_HASH
        (11, 24), # DT_SYMENT
        (10, len(strtab)),  # DT_STRSZ
        (14, soname_off),   # DT_SONAME
        (0, 0),   # DT_NULL
    ]

    # ---- 布局 ----
    off = text_vaddr + len(text)
    hash_addr = off
    off += len(hash_tbl)
    symtab_addr = off
    off += len(symtab)
    strtab_addr = off
    off += len(strtab)
    dynamic_addr = off
    dyn_entries[0] = (6, symtab_addr)
    dyn_entries[1] = (5, strtab_addr)
    dyn_entries[2] = (4, hash_addr)
    dynamic = b"".join(struct.pack("<qQ", t, v) for t, v in dyn_entries)
    off += len(dynamic)
    total = off

    # ---- ELF header ----
    eh = bytearray(64)
    eh[0:16] = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\0" * 8
    struct.pack_into("<HHIQQQIHHHHHH", eh, 16,
                     3,       # e_type = ET_DYN
                     183,     # e_machine = EM_AARCH64
                     1,       # e_version
                     0,       # e_entry
                     64,      # e_phoff
                     0,       # e_shoff
                     0,       # e_flags
                     64,      # e_ehsize
                     56,      # e_phentsize
                     2,       # e_phnum
                     64,      # e_shentsize
                     0,       # e_shnum
                     0)       # e_shstrndx

    # ---- Program headers ----
    # 格式 <IIQQQQQQ: p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align
    ph_load = struct.pack("<IIQQQQQQ",
                          1,             # p_type = PT_LOAD
                          7,             # p_flags = R|W|X（.dynamic 需可写）
                          0,             # p_offset
                          0,             # p_vaddr
                          0,             # p_paddr
                          total,         # p_filesz
                          total,         # p_memsz
                          0x1000)        # p_align
    ph_dyn = struct.pack("<IIQQQQQQ",
                         2,              # p_type = PT_DYNAMIC
                         6,              # p_flags = R|W
                         dynamic_addr,   # p_offset
                         dynamic_addr,   # p_vaddr
                         dynamic_addr,   # p_paddr
                         len(dynamic),   # p_filesz
                         len(dynamic),   # p_memsz
                         8)              # p_align

    blob = bytes(eh) + ph_load + ph_dyn + text + hash_tbl + bytes(symtab) + strtab + dynamic
    assert len(blob) == total, f"{len(blob)} != {total}"
    with open(OUT, "wb") as f:
        f.write(blob)
    print("written:", OUT, total, "bytes")
    return blob


if __name__ == "__main__":
    blob = build()
    # 反汇编校验导出符号存在
    import subprocess, re
    out = subprocess.run(["objdump", "-d", "-b", "elf64-littleaarch64", OUT], capture_output=True, text=True).stderr
    # winlibs objdump 不支持 aarch64，改用 capstone 自校验
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    n = 0
    for ins in md.disasm(blob[0xB0:0xB0+256], 0xB0):
        n += 1
        if n > 12:
            break
    print("first insns OK")
