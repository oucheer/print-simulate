# -*- coding: utf-8 -*-
"""repair build_initramfs.py: CMD REG TABLE uses gdb -x command file (fix while encoding)"""
p = r"tools\build_initramfs.py"
s = open(p, encoding="utf-8").read()
old = 'echo "--- CMD REG TABLE ---"; timeout 60 gdb -p $MFP -batch -ex "set pagination off" -ex "set \\$h=*(long*)0x910e20" -ex "x/16gx \\$h" -ex "x/24gx 0x910e20" -ex "detach" 2>&1 | tail -60;'
new = ('echo "--- CMD REG TABLE ---"; echo "set pagination off" > /tmp/gdbcmd.txt; '
       'echo "set \\$h = *(long*)0x910e20" >> /tmp/gdbcmd.txt; '
       'echo "set \\$i = 0" >> /tmp/gdbcmd.txt; '
       'echo "while \\$h != 0 && \\$i < 60" >> /tmp/gdbcmd.txt; '
       'echo "printf \\"node=%p cmd=%#x cb=%p arg=%p\\\\n\\", \\$h, *(int*)(\\$h+0x10), *(long*)(\\$h+0x18), *(long*)(\\$h+0x20)" >> /tmp/gdbcmd.txt; '
       'echo "set \\$h = *(long*)\\$h" >> /tmp/gdbcmd.txt; '
       'echo "set \\$i = \\$i + 1" >> /tmp/gdbcmd.txt; '
       'echo "end" >> /tmp/gdbcmd.txt; '
       'echo "detach" >> /tmp/gdbcmd.txt; '
       'timeout 60 gdb -p $MFP -batch -x /tmp/gdbcmd.txt 2>&1 | tail -90;')
n = s.count(old)
print("found", n)
if n == 1:
    open(p, "w", encoding="utf-8").write(s.replace(old, new))
    print("replaced OK")
else:
    # try shorter anchor
    short = '-ex "x/24gx 0x910e20" -ex "detach" 2>&1 | tail -60;'
    m = s.count(short)
    print("short anchor count", m)
