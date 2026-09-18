# -*- coding: utf-8 -*-
"""round 66: gdb call pi_sem_post_ent（字节偏移 912/936/944）唤醒 lpd/port913x/netdata"""
p = r"tools/build_initramfs.py"
s = open(p, encoding="utf-8").read()

start_marker = "2>&1 | tail -6; sleep 45;"
end_marker = "echo done'"
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new_block = r'''2>&1 | tail -6; sleep 45; echo "--- CHECK ALIVE ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- WAKE SEM ---"; gdb -p $MFP -batch -ex "set pagination off" -ex "set confirm off" -ex "p/x &s_semaphore_pool" -ex "call (int)pi_sem_post_ent((char*)&s_semaphore_pool+912, 0)" -ex "call (int)pi_sem_post_ent((char*)&s_semaphore_pool+936, 0)" -ex "call (int)pi_sem_post_ent((char*)&s_semaphore_pool+944, 0)" -ex "detach" 2>&1 | tail -10; sleep 20; echo "--- LISTEN 1 ---"; cat /proc/net/tcp 2>&1 | head -25; echo "--- ALIVE 2 ---"; ls /proc/$MFP/task 2>&1 | wc -l; echo "--- UNIX COUNT ---"; cat /proc/net/unix 2>&1 | wc -l; echo "--- SOCK FDS ---"; ls -l /proc/$MFP/fd 2>&1 | grep -c socket; sleep 60; echo "--- LISTEN FINAL ---"; cat /proc/net/tcp 2>&1 | head -25; echo "--- MFP LOG TAIL ---"; tail -c 30000 /tmp/mfp.log 2>&1 | tail -30; echo done' '''

s = s[:i] + new_block + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")
