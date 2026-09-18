# -*- coding: utf-8 -*-
"""Make gdbpatch fire once; add retry to LPD ENABLE gdb; lengthen port poll."""
import io

path = r'd:\Apps\codex\files\simulate\tools\build_initramfs.py'
with io.open(path, 'r', encoding='utf-8') as f:
    src = f.read()

old1 = r'echo "set pagination off" > /tmp/gdbpatch.txt;'
new1 = r'if [ -z "$PATCHED" ]; then echo "set pagination off" > /tmp/gdbpatch.txt;'
assert src.count(old1) == 1, 'patch-anchor1'
src = src.replace(old1, new1, 1)

old2 = r'timeout 30 gdb -p $MFP -batch -x /tmp/gdbpatch.txt 2>&1 | tail -6; if [ $((i % 9)) -eq 0 ]; then'
new2 = r'timeout 30 gdb -p $MFP -batch -x /tmp/gdbpatch.txt 2>&1 | tail -6; PATCHED=1; fi; if [ $((i % 9)) -eq 0 ]; then'
assert src.count(old2) == 1, 'patch-anchor2'
src = src.replace(old2, new2, 1)

old3 = (r'timeout 40 gdb -p $MFP -batch -x /tmp/gdblpd.txt 2>&1 | tail -10; '
        r'sleep 3; ')
new3 = (r'sleep 3; for t in 1 2 3; do '
        r'timeout 40 gdb -p $MFP -batch -x /tmp/gdblpd.txt > /tmp/gdblpd.out 2>&1; rc=$?; '
        r'tail -12 /tmp/gdblpd.out; if [ $rc -eq 0 ]; then break; fi; '
        r'echo "GDBLPD_RETRY_$t"; sleep 5; done; '
        r'sleep 3; ')
assert src.count(old3) == 1, 'patch-anchor3'
src = src.replace(old3, new3, 1)

old4 = r'for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 5; echo "PORTS_T+$((i*5))";'
new4 = r'for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do sleep 10; echo "PORTS_T+$((i*10))";'
assert src.count(old4) == 1, 'patch-anchor4'
src = src.replace(old4, new4, 1)

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(src)
print('robustness patch OK')
