# -*- coding: utf-8 -*-
"""Add wired-speed notify + listener poll to the LPD block in build_initramfs.py."""
import io

path = r'd:\Apps\codex\files\simulate\tools\build_initramfs.py'
with io.open(path, 'r', encoding='utf-8') as f:
    src = f.read()

old_lpd = (r'echo "set \$r = ((long(*)(void*))0x684068)(\$h)" >> /tmp/gdblpd.txt; '
           r'echo "printf \"LPD_PROLOG_RC=%d\\n\", \$r" >> /tmp/gdblpd.txt; ')
new_lpd = (r'echo "set \$r = ((long(*)(void*))0x684068)(\$h)" >> /tmp/gdblpd.txt; '
           r'echo "printf \"LPD_PROLOG_RC=%d\\n\", \$r" >> /tmp/gdblpd.txt; '
           r'echo "set \$r2 = ((long(*)(void*, int, int))0x61a758)(\$ctx, 100, 0)" >> /tmp/gdblpd.txt; '
           r'echo "printf \"WIRED_RC=%d\\n\", \$r2" >> /tmp/gdblpd.txt; ')
assert src.count(old_lpd) == 1, 'lpd anchor not found'
src = src.replace(old_lpd, new_lpd, 1)

old_ports = (r'echo "--- LPD PORTS AFTER ---"; '
             r'cat /proc/net/tcp 2>&1 | awk "{print \$2, \$4}"; '
             r'echo "--- PORTS ALL ---";')
new_ports = (r'echo "--- LPD PORTS AFTER ---"; '
             r'for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 5; '
             r'echo "PORTS_T+$((i*5))"; '
             r'cat /proc/net/tcp 2>&1 | awk "{print \$2, \$4}"; done; '
             r'echo "--- PORTS ALL ---";')
assert src.count(old_ports) == 1, 'ports anchor not found'
src = src.replace(old_ports, new_ports, 1)

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(src)
print('wired-speed patch OK')
