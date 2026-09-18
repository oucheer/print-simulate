import sys, pathlib
sys.path.insert(0,'/mnt/data/printer-sim-poc')
from ext4_read import Ext4
root=pathlib.Path(sys.argv[2]); root.mkdir(parents=True,exist_ok=True)
e=Ext4(sys.argv[1])
for p in sys.argv[3:]:
    ino=e.find(p)
    if ino is None:
        print('MISSING',p); continue
    n,d=e.read_inode(ino)
    out=root/p
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(d)
    print('OK',p,len(d),'mode',oct(n['mode']))
e.close()
