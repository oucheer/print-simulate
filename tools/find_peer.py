# -*- coding: utf-8 -*-
"""定位 _wait_for_peer 符号：在 mfp.afx 还是 libosal.so？导出还是本地？"""
import struct

def load_symbols(path):
    data = open(path, "rb").read()
    if data[:4] != b"\x7fELF":
        return None, None
    is64 = data[4] == 2
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
    def read_str(sec, off):
        d = data[sec[4]:sec[4] + sec[5]]
        e = d.index(b"\0", off)
        return d[off:e].decode(errors="replace")
    out = {}
    for tbl_name in (".symtab", ".dynsym"):
        if tbl_name not in by:
            continue
        st = by[tbl_name]
        linked = by.get(sec_name(st[6]))
        entsize = st[9] or 24
        for i in range(st[5] // entsize):
            e = struct.unpack_from(endian + "IBBHQQ", data, st[4] + i * entsize)
            name = read_str(linked, e[0]) if linked else ""
            st_info, st_value = e[1], e[4]
            if name:
                out.setdefault(name, []).append((tbl_name, st_value, st_info))
    return data, out

for path in [r"runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx",
             r"runtime\unpacked\rkaf\rootfs\usr\lib\libosal.so",
             r"runtime\unpacked\rkaf\rootfs\usr\lib\libcbinder.so"]:
    try:
        data, syms = load_symbols(path)
    except Exception as ex:
        print(path, "ERR", ex)
        continue
    if syms is None:
        print(path, "no ELF")
        continue
    print(f"\n==== {path} ====")
    hits = [k for k in syms if "wait_peer" in k or "binder_call" in k or "binder_" in k]
    for h in sorted(hits):
        for tbl, v, info in syms[h]:
            stt = info & 0xF
            stb = info >> 4
            print(f"  {tbl} 0x{v:08x} type={stt} bind={stb} {h}")
    # 统计 binder 相关
    print("  binder-syms:", len(hits))
