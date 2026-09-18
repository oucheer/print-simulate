"""反汇编 mfp.afx 的 LPD 开关相关符号: netdata_get_lpd_switch / net_lpd_enable / lpd_prolog 等"""
import struct
import sys
from capstone import *

path = r'd:\Apps\codex\files\simulate\runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx'
if len(sys.argv) > 1:
    path = sys.argv[1]

with open(path, 'rb') as f:
    data = f.read()

endian = '<'
e_shoff = struct.unpack_from(endian + 'Q', data, 0x28)[0]
e_shentsize = struct.unpack_from(endian + 'H', data, 0x3A)[0]
e_shnum = struct.unpack_from(endian + 'H', data, 0x3C)[0]
e_shstrndx = struct.unpack_from(endian + 'H', data, 0x3E)[0]

shstr_off = struct.unpack_from(endian + 'Q', data, e_shoff + e_shstrndx * e_shentsize + 0x18)[0]
shstr_size = struct.unpack_from(endian + 'Q', data, e_shoff + e_shstrndx * e_shentsize + 0x20)[0]
shstr = data[shstr_off:shstr_off + shstr_size]


def sh(i, fo):
    return struct.unpack_from(endian + 'Q', data, e_shoff + i * e_shentsize + fo)[0]


def secname(i):
    off = struct.unpack_from(endian + 'I', data, e_shoff + i * e_shentsize + 0x00)[0]
    try:
        end = shstr.index(b'\0', off)
        return shstr[off:end].decode()
    except ValueError:
        return ''


secs = {}
for i in range(e_shnum):
    n = secname(i)
    if n:
        secs[n] = i

dynsym_off = sh(secs['.dynsym'], 0x18)
dynsym_size = sh(secs['.dynsym'], 0x20)
dynstr_off = sh(secs['.dynstr'], 0x18)
dynstr_size = sh(secs['.dynstr'], 0x20)
text_vaddr = sh(secs['.text'], 0x10)
text_off = sh(secs['.text'], 0x18)

dynsym = data[dynsym_off:dynsym_off + dynsym_size]
dynstr = data[dynstr_off:dynstr_off + dynstr_size]

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

WANT = ('netdata_get_lpd_switch', 'netdata_set_lpd_switch', 'net_lpd_enable',
        'net_lpd_disable', 'lpd_prolog', 'lpd_switch_change', 'lpd_start_job',
        'netdata_get_ipp_switch', 'netdata_set_ipp_switch')

targets = {}
for i in range(0, len(dynsym), 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(endian + 'IBBHQQ', dynsym, i)
    if st_name == 0 or st_value == 0:
        continue
    end = dynstr.find(b'\0', st_name)
    if end < 0:
        continue
    name = dynstr[st_name:end].decode(errors='replace')
    if name in WANT:
        targets.setdefault(name, []).append((st_value, st_size, st_shndx))
        print('FOUND %s: vaddr=0x%x size=0x%x shndx=%d' % (name, st_value, st_size, st_shndx))

for name, entries in targets.items():
    for addr, size, shndx in entries:
        if shndx != secs.get('.text', -1):
            continue
        n = size if size else 0x60
        fo = text_off + (addr - text_vaddr)
        code = data[fo:fo + n]
        print('\n=== %s @ 0x%x (size=0x%x) ===' % (name, addr, size))
        cnt = 0
        for ins in md.disasm(code, addr):
            print('  0x%x: %-9s %s' % (ins.address, ins.mnemonic, ins.op_str))
            cnt += 1
            if cnt > 40:
                break
