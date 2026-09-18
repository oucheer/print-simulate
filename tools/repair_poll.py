# -*- coding: utf-8 -*-
"""repair build_initramfs.py POLL: attach gdb every 3rd round only, wait otherwise"""
p = r"tools\build_initramfs.py"
s = open(p, encoding="utf-8").read()
old = 'if [ "$N" -le 4 ]; then echo "POLL: early init, no gdb attach"; sleep 10; continue; fi; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set print thread-events off" -ex "set *(unsigned char*)(0xa91370+0x5c)=1" -ex "set *(unsigned int*)(0xa91370+0x7c)=1" -ex "set *(unsigned short*)(0xa91370+0x80)=1" -ex "set *(unsigned char*)(0xa91370+0x82)=1" -ex "detach" 2>&1 | tail -1; if [ $((i % 4)) -eq 0 ]; then echo "--- BT@POLL$i ---";'
new = 'if [ "$N" -le 10 ]; then echo "POLL: early init, no gdb attach"; sleep 10; continue; fi; if [ $((i % 3)) -ne 0 ]; then echo "POLL: wait only, no attach"; sleep 15; continue; fi; timeout 30 gdb -p $MFP -batch -ex "set pagination off" -ex "set print thread-events off" -ex "set *(unsigned char*)(0xa91370+0x5c)=1" -ex "set *(unsigned int*)(0xa91370+0x7c)=1" -ex "set *(unsigned short*)(0xa91370+0x80)=1" -ex "set *(unsigned char*)(0xa91370+0x82)=1" -ex "detach" 2>&1 | tail -1; if [ $((i % 9)) -eq 0 ]; then echo "--- BT@POLL$i ---";'
n = s.count(old)
print("found", n)
if n == 1:
    open(p, "w", encoding="utf-8").write(s.replace(old, new))
    print("replaced OK")
