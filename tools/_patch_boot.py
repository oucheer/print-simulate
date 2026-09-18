path = r"D:\Apps\codex\files\simulate\tools\build_initramfs.py"
txt = open(path, encoding="utf-8").read()
B = chr(92)   # single backslash

old1 = r"(\$ctx, 100, 0)"
assert txt.count(old1) == 1, "anchor1"
txt = txt.replace(old1, r"(\$ctx, 100, 1)")

anchor2 = 'echo "set ' + B + '$r = ((long(*)(void*))0x684068)(' + B + '$h)" >> /tmp/gdblpd.txt;'
c2 = txt.count(anchor2)
assert c2 == 1, "anchor2: %d" % c2
E = 'echo '
GT = '" >> /tmp/gdblpd.txt; '
ins2 = (
    E + '"set *(unsigned int*)0x5fdac8 = 0x52800020"' + GT +
    E + '"set *(unsigned int*)0x5fdacc = 0xd65f03c0"' + GT +
    E + '"set ' + B + '$r0 = ((long(*)(void*, int, int))0x61fa9c)(' + B + '$ctx, 1, 0)"' + GT +
    E + '"printf ' + B + '"SETSWITCH_RC=%d' + B + B + 'n' + B + '", ' + B + '$r0"' + GT
)
txt = txt.replace(anchor2, ins2 + anchor2)

anchor3 = 'echo "b *0x74c960" >> /tmp/gdbtrace.txt;'
c3 = txt.count(anchor3)
assert c3 == 1, "anchor3: %d" % c3
GT2 = '" >> /tmp/gdbtrace.txt; '
def lpd_bp(addr, tag):
    return (
        E + '"b *' + addr + '"' + GT2 +
        E + '"commands"' + GT2 +
        E + '"silent"' + GT2 +
        E + '"printf ' + B + '"TRACE HIT ' + tag + B + B + 'n' + B + '""' + GT2 +
        E + '"continue"' + GT2 +
        E + '"end"' + GT2
    )
ins3 = (lpd_bp("0x683e0c", "lpd_netproxy_handler") +
        lpd_bp("0x68365c", "lpd_dispatch_thread") +
        lpd_bp("0x6830a4", "lpd_start_job") +
        lpd_bp("0x68236c", "lpd_task_read") +
        lpd_bp("0x6831e8", "lpd_list_add"))
txt = txt.replace(anchor3, ins3 + anchor3)

open(path, "w", encoding="utf-8", newline="\n").write(txt)
print("patched OK")
