# -*- coding: utf-8 -*-
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()
old = r'''echo "--- MFP LOG AFTER INJECT WINDOW ---"; grep -aE "==>|recvStruct|pedk|578|0x578|print" /tmp/mfp.log | tail -35; '''
new = r'''echo "--- MFP LOG AFTER INJECT WINDOW ---"; tail -c 20000 /tmp/mfp.log | grep -avE "_wait_for_peer" | tail -40; echo "--- BT SNAPSHOT ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set height 0" -ex "thread apply all bt 1" -ex "detach" > /tmp/bt2.txt 2>&1; grep -E "0x74f9|0x73b3|0x4b0d|0x74fb|0x74c3|accept|socket|select" /tmp/bt2.txt | head -15; '''
assert old in s, "grep block not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")