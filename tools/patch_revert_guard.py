# -*- coding: utf-8 -*-
"""Revert PATCHED guard: restore repeated gdbpatch every poll (flags get cleared by fw)."""
import io

path = r'd:\Apps\codex\files\simulate\tools\build_initramfs.py'
with io.open(path, 'r', encoding='utf-8') as f:
    src = f.read()

old1 = r'if [ -z "$PATCHED" ]; then echo "set pagination off" > /tmp/gdbpatch.txt;'
new1 = r'echo "set pagination off" > /tmp/gdbpatch.txt;'
assert src.count(old1) == 1, 'anchor1'
src = src.replace(old1, new1, 1)

old2 = r'tail -6; PATCHED=1; fi; if [ $((i % 9)) -eq 0 ]; then'
new2 = r'tail -6; if [ $((i % 9)) -eq 0 ]; then'
assert src.count(old2) == 1, 'anchor2'
src = src.replace(old2, new2, 1)

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(src)
print('PATCHED guard reverted OK')
