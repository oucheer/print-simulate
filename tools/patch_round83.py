# -*- coding: utf-8 -*-
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()
old = r'''echo "--- MFP LOG AFTER INJECT ---"; grep -aE "==>|recvStruct|pedk_mgr|module|578" /tmp/mfp.log | tail -25; echo "--- NC LOGS ---"; cat /tmp/nc1.log 2>&1 | head -3; cat /tmp/nc2.log 2>&1 | head -3; '''
new = r'''echo "READY FOR INJECT"; sleep 120; echo "--- MFP LOG AFTER INJECT WINDOW ---"; grep -aE "==>|recvStruct|pedk|578|0x578|print" /tmp/mfp.log | tail -35; '''
assert old in s, "old inject not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")