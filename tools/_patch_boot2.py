path = r"D:\Apps\codex\files\simulate\tools\build_initramfs.py"
txt = open(path, encoding="utf-8").read()
B = chr(92)
Q = chr(34)
QQ = Q + Q

def rep(old, new, expect):
    c = txt_count(old)
    assert c == expect, "count=%d expect=%d for %r" % (c, expect, old)
    return txt.replace(old, new)

def txt_count(s):
    return txt.count(s)

# tag printf lines: ...\\n\""" >> -> ...\\n\"" >>
tags = ["lpd_netproxy_handler", "lpd_dispatch_thread", "lpd_start_job", "lpd_task_read", "lpd_list_add"]
for tag in tags:
    old = "TRACE HIT " + tag + B + B + "n" + B + Q + Q + Q + " >> /tmp/gdbtrace.txt;"
    new = "TRACE HIT " + tag + B + B + "n" + B + Q + Q + " >> /tmp/gdbtrace.txt;"
    c = txt_count(old)
    assert c == 1, "tag %s count=%d" % (tag, c)
    txt = txt.replace(old, new)

fixes = [
    ("= 0x52800020" + QQ + " >>", "= 0x52800020" + Q + " >>", 1),
    ("= 0xd65f03c0" + QQ + " >>", "= 0xd65f03c0" + Q + " >>", 1),
    (", 1, 0)" + QQ + " >>", ", 1, 0)" + Q + " >>", 1),
    (B + "$r0" + QQ + " >>", B + "$r0" + Q + " >>", 1),
]
for addr in ["0x683e0c", "0x68365c", "0x6830a4", "0x68236c", "0x6831e8"]:
    fixes.append(("b *" + addr + QQ + " >>", "b *" + addr + Q + " >>", 1))
for kw in ["commands", "silent", "continue", "end"]:
    fixes.append((Q + kw + QQ + " >>", Q + kw + Q + " >>", 5))

for old, new, expect in fixes:
    c = txt_count(old)
    assert c == expect, "count=%d expect=%d for %r" % (c, expect, old)
    txt = txt.replace(old, new)

open(path, "w", encoding="utf-8", newline="\n").write(txt)
print("all fixed OK")
