# -*- coding: utf-8 -*-
"""Fix escaping in the LPD block inserted into build_initramfs.py."""
import io

path = r'd:\Apps\codex\files\simulate\tools\build_initramfs.py'
with io.open(path, 'r', encoding='utf-8') as f:
    src = f.read()

pairs = [
    (r'echo "set $h = *(long*)0xa92298"', r'echo "set \$h = *(long*)0xa92298"'),
    (r'\", $h" >> /tmp/gdblpd.txt', r'\", \$h" >> /tmp/gdblpd.txt'),
    (r'echo "set $ctx = *(long*)($h+0x10)"', r'echo "set \$ctx = *(long*)(\$h+0x10)"'),
    (r'\", $ctx, *(unsigned int*)($ctx+0xb30)"', r'\", \$ctx, *(unsigned int*)(\$ctx+0xb30)"'),
    (r'echo "set *(unsigned int*)($ctx+0xb30) = 1"', r'echo "set *(unsigned int*)(\$ctx+0xb30) = 1"'),
    (r'\", *(unsigned int*)($ctx+0xb30)" >> /tmp/gdblpd.txt', r'\", *(unsigned int*)(\$ctx+0xb30)" >> /tmp/gdblpd.txt'),
    (r'echo "set $r = ((long(*)(void*))0x684068)($h)"', r'echo "set \$r = ((long(*)(void*))0x684068)(\$h)"'),
    (r'\", $r" >> /tmp/gdblpd.txt', r'\", \$r" >> /tmp/gdblpd.txt'),
    (r"awk '{print $2, $4}'", r'awk "{print \$2, \$4}"'),
]
for old, new in pairs:
    n = src.count(old)
    assert n == 1, 'expect 1 occurrence, got %d for: %s' % (n, old[:50])
    src = src.replace(old, new, 1)

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(src)
print('escape fixes OK')
