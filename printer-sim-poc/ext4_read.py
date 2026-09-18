import struct, sys
from pathlib import Path

class Ext4:
    def __init__(self,p):
        self.p=Path(p); self.f=self.p.open('rb')
        self.f.seek(1024); sb=self.f.read(1024)
        if struct.unpack_from('<H',sb,0x38)[0]!=0xef53: raise ValueError('not ext4')
        self.block=1024<<struct.unpack_from('<I',sb,0x18)[0]
        self.blocks=struct.unpack_from('<I',sb,4)[0]
        self.bpg=struct.unpack_from('<I',sb,0x20)[0]
        self.ipg=struct.unpack_from('<I',sb,0x28)[0]
        self.isize=struct.unpack_from('<H',sb,0x58)[0]
        self.incompat=struct.unpack_from('<I',sb,0x60)[0]
        self.desc_size=struct.unpack_from('<H',sb,0xFE)[0] or 32
        self.groups=(self.blocks+self.bpg-1)//self.bpg
        self.gdt_block=2 if self.block==1024 else 1
        self.gdt_off=self.gdt_block*self.block
        self.gdt=[]
        self.f.seek(self.gdt_off); g=self.f.read(self.groups*self.desc_size)
        for i in range(self.groups):
            d=g[i*self.desc_size:(i+1)*self.desc_size]
            it=struct.unpack_from('<I',d,8)[0]
            self.gdt.append(it)
    def inode(self,ino):
        gi=(ino-1)//self.ipg; idx=(ino-1)%self.ipg
        off=self.gdt[gi]*self.block + idx*self.isize
        self.f.seek(off); b=self.f.read(self.isize)
        mode=struct.unpack_from('<H',b,0)[0]
        size_lo=struct.unpack_from('<I',b,4)[0]; size_hi=struct.unpack_from('<I',b,108)[0]
        size=size_lo | (size_hi<<32)
        flags=struct.unpack_from('<I',b,32)[0]
        return {'ino':ino,'mode':mode,'size':size,'flags':flags,'raw':b}
    def extents(self, raw, flags):
        if not (flags & 0x80000): return self.block_ptrs(raw)
        eh_magic, eh_entries, eh_max, eh_depth = struct.unpack_from('<HHHH', raw, 40)
        if eh_magic != 0xF30A: return []
        return self._extent_node(raw,40,eh_depth)
    def _extent_node(self, data, off, depth):
        _, entries, _, _=struct.unpack_from('<HHHH',data,off)
        out=[]
        if depth==0:
            for i in range(entries):
                po=off+12+i*12
                ee_block, ee_len, ee_start_hi, ee_start_lo=struct.unpack_from('<IHHI',data,po)
                if ee_len==0: continue
                n=ee_len & 0x7fff
                start=(ee_start_hi<<32)|ee_start_lo
                out.append((ee_block,n,start))
        else:
            # index entries: logical block, leaf physical block hi/lo
            for i in range(entries):
                po=off+12+i*12
                _, leaf_lo, leaf_hi, _=struct.unpack_from('<IIHH',data,po)
                leaf=(leaf_hi<<32)|leaf_lo
                self.f.seek(leaf*self.block); child=self.f.read(self.block)
                out += self._extent_node(child,0,depth-1)
        return out
    def block_ptrs(self, raw):
        ptrs=struct.unpack_from('<15I',raw,40)
        out=[]
        for p in ptrs[:12]:
            if p: out.append((None,1,p))
        # skip indirect for PoC
        return out
    def read_inode(self,ino):
        n=self.inode(ino)
        ext=self.extents(n['raw'],n['flags'])
        data=bytearray(n['size'])
        for logical,count,phys in ext:
            if logical is None: logical=len([x for x in ext if x[0] is not None])
            # extent entries sorted; copy blocks
            for j in range(count):
                dst=(logical+j)*self.block
                if dst>=len(data): break
                self.f.seek((phys+j)*self.block); chunk=self.f.read(min(self.block,len(data)-dst))
                data[dst:dst+len(chunk)]=chunk
        return n,bytes(data)
    def dirents(self,ino):
        n,data=self.read_inode(ino)
        pos=0
        while pos+8<=len(data):
            ent_ino, rec_len, name_len, file_type=struct.unpack_from('<IHBB',data,pos)
            if rec_len<8: break
            name=data[pos+8:pos+8+name_len].decode('utf-8','replace')
            if ent_ino: yield ent_ino,name,file_type
            pos+=rec_len
    def find(self,path):
        ino=2
        for comp in [x for x in path.split('/') if x]:
            found=None
            for e,n,_ in self.dirents(ino):
                if n==comp: found=e; break
            if found is None: return None
            ino=found
        return ino
    def close(self): self.f.close()

if __name__=='__main__':
    e=Ext4(sys.argv[1])
    print(e.block,e.blocks,e.groups,e.ipg,e.isize,hex(e.incompat))
    for p in sys.argv[2:]:
      ino=e.find(p); print(p,ino)
      if ino:
       n,d=e.read_inode(ino); print('mode',oct(n['mode']),'size',n['size'],'first',d[:80])
    e.close()
