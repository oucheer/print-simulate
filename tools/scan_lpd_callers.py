
import struct
PATH = r'D:\Apps\codex\files\simulate\runtime\unpacked\rkaf\rootfs\usr\bin\mfp.afx'
TARGETS = {
    0x684068: 'lpd_prolog',
    0x5fdac8: 'netdata_get_lpd_switch',
    0x61fa9c: 'netdata_set_lpd_switch',
    0x5fde78: 'netdata_get_ipp_switch',
    0x621988: 'netdata_set_ipp_switch',
    0x74c560: 'lpd_listen_service',
    0x61a758: 'netdata_set_wired_speed',
}
data = open(PATH, 'rb').read()
e_phoff = struct.unpack_from('<Q', data, 0x20)[0]
e_phentsize = struct.unpack_from('<H', data, 0x36)[0]
e_phnum = struct.unpack_from('<H', data, 0x38)[0]
segs = []
for i in range(e_phnum):
    off = e_phoff + i * e_phentsize
    p_type, p_flags = struct.unpack_from('<II', data, off)
    p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from('<QQQQQ', data, off + 8)
    if p_type == 1:
        segs.append((p_vaddr, p_filesz, p_offset, p_flags))
hits = []
for vaddr, filesz, offset, flags in segs:
    if not (flags & 1):
        continue
    text = data[offset:offset + filesz]
    tva = vaddr
    for off in range(0, len(text) - 4, 4):
        w = struct.unpack_from('<I', text, off)[0]
        if (w >> 26) == 0x25:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            target = tva + off + imm * 4
            if target in TARGETS:
                hits.append((tva + off, TARGETS[target]))
for site, name in sorted(hits):
    print('BL from 0x%x -> %s' % (site, name))
print('total hits: %d' % len(hits))
