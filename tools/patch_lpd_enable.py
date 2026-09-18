# -*- coding: utf-8 -*-
"""Patch build_initramfs.py SIMBOOT: add LPD-enable gdb batch + mfp.log upload + longer inject window."""
import io

path = r'd:\Apps\codex\files\simulate\tools\build_initramfs.py'
with io.open(path, 'r', encoding='utf-8') as f:
    src = f.read()

# 1) Insert LPD-enable gdb batch right before "--- PORTS ALL ---"
anchor1 = 'echo "--- PORTS ALL ---";'
lpd_block = (
    'echo "--- LPD ENABLE ---"; '
    'echo "set pagination off" > /tmp/gdblpd.txt; '
    'echo "set print thread-events off" >> /tmp/gdblpd.txt; '
    'echo "set $h = *(long*)0xa92298" >> /tmp/gdblpd.txt; '
    'echo "printf \\"HANDLE=%p\\\\n\\", $h" >> /tmp/gdblpd.txt; '
    'echo "set $ctx = *(long*)($h+0x10)" >> /tmp/gdblpd.txt; '
    'echo "printf \\"CTX=%p SW_B4=%d\\\\n\\", $ctx, *(unsigned int*)($ctx+0xb30)" >> /tmp/gdblpd.txt; '
    'echo "set *(unsigned int*)($ctx+0xb30) = 1" >> /tmp/gdblpd.txt; '
    'echo "printf \\"SW_AF=%d\\\\n\\", *(unsigned int*)($ctx+0xb30)" >> /tmp/gdblpd.txt; '
    'echo "set $r = ((long(*)(void*))0x684068)($h)" >> /tmp/gdblpd.txt; '
    'echo "printf \\"LPD_PROLOG_RC=%d\\\\n\\", $r" >> /tmp/gdblpd.txt; '
    'echo "detach" >> /tmp/gdblpd.txt; '
    'timeout 40 gdb -p $MFP -batch -x /tmp/gdblpd.txt 2>&1 | tail -10; '
    'sleep 3; '
    'echo "--- LPD PORTS AFTER ---"; '
    'cat /proc/net/tcp 2>&1 | awk \'{print $2, $4}\'; '
    'echo "--- PORTS ALL ---";'
)
assert anchor1 in src, 'anchor1 not found'
src = src.replace(anchor1, lpd_block, 1)

# 2) Widen inject window 120 -> 900
old2 = 'echo "READY FOR INJECT"; sleep 120;'
new2 = 'echo "READY FOR INJECT"; sleep 900;'
assert old2 in src, 'anchor2 not found'
src = src.replace(old2, new2, 1)

# 3) Also upload mfp.log for trace extraction
old3 = 'echo "VHAL_UPLOAD_RC=$?";'
new3 = ('echo "VHAL_UPLOAD_RC=$?"; '
        'wget -q -O /dev/null --post-file=/tmp/mfp.log http://10.0.2.2:8001/upload/mfp.log 2>&1; '
        'echo "MFP_UPLOAD_RC=$?";')
assert old3 in src, 'anchor3 not found'
src = src.replace(old3, new3, 1)

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(src)
print('patched OK')
