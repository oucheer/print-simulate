#!/usr/bin/env python3
"""Printer Simulation PoC v0.1

Goals:
- Parse a Rockchip RKFW update image without vendor tools.
- Extract the embedded RKAF image and selected rootfs files from ext4.
- Inspect the real AArch64 mfp.afx and its HAL boundary.
- Build a minimal Virtual HAL / Printer device model and run deterministic scenarios.

This PoC deliberately does NOT claim to execute AArch64 mfp.afx on the host.
That requires an ARM64 emulator (e.g. qemu-aarch64) and a compatible userland.
The PoC instead proves the evidence-driven model and the virtual device loop.
"""
from __future__ import annotations
import argparse, hashlib, json, re, struct, subprocess, sys, textwrap
from dataclasses import dataclass, asdict, field
from pathlib import Path

RKFW = b"RKFW"
RKAF = b"RKAF"


def cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


class Ext4Reader:
    def __init__(self, path: Path):
        self.path=path; self.f=path.open('rb')
        self.f.seek(1024); sb=self.f.read(1024)
        if struct.unpack_from('<H', sb, 0x38)[0] != 0xEF53:
            raise ValueError(f"{path} is not ext4")
        self.block = 1024 << struct.unpack_from('<I', sb, 0x18)[0]
        self.blocks = struct.unpack_from('<I', sb, 4)[0]
        self.bpg = struct.unpack_from('<I', sb, 0x20)[0]
        self.ipg = struct.unpack_from('<I', sb, 0x28)[0]
        self.isize = struct.unpack_from('<H', sb, 0x58)[0]
        self.incompat = struct.unpack_from('<I', sb, 0x60)[0]
        self.groups = (self.blocks + self.bpg - 1)//self.bpg
        self.desc_size = struct.unpack_from('<H', sb, 0xFE)[0] or 32
        self.gdt_block = 2 if self.block == 1024 else 1
        self.f.seek(self.gdt_block*self.block)
        gdt=self.f.read(self.groups*self.desc_size)
        self.inode_tables=[]
        for i in range(self.groups):
            self.inode_tables.append(struct.unpack_from('<I', gdt, i*self.desc_size+8)[0])

    def inode(self, ino: int):
        gi=(ino-1)//self.ipg; idx=(ino-1)%self.ipg
        off=self.inode_tables[gi]*self.block + idx*self.isize
        self.f.seek(off); raw=self.f.read(self.isize)
        mode=struct.unpack_from('<H',raw,0)[0]
        size=struct.unpack_from('<I',raw,4)[0] | (struct.unpack_from('<I',raw,108)[0]<<32)
        flags=struct.unpack_from('<I',raw,32)[0]
        return mode,size,flags,raw

    def _extent_node(self, buf: bytes, off: int, depth: int):
        magic, entries, _max, _depth = struct.unpack_from('<HHHH', buf, off)
        if magic != 0xF30A: return []
        out=[]
        if depth == 0:
            for i in range(entries):
                p=off+12+i*12
                logical, length, hi, lo=struct.unpack_from('<IHHI',buf,p)
                out.append((logical, length & 0x7FFF, (hi<<32)|lo))
        else:
            for i in range(entries):
                p=off+12+i*12
                logical, lo, hi, unused=struct.unpack_from('<IIHH',buf,p)
                block=(hi<<32)|lo
                self.f.seek(block*self.block); child=self.f.read(self.block)
                out.extend(self._extent_node(child,0,depth-1))
        return out

    def read_inode(self, ino:int):
        mode,size,flags,raw=self.inode(ino)
        extents=[]
        if flags & 0x80000:
            extents=self._extent_node(raw,40,struct.unpack_from('<H',raw,46)[0])
        else:
            for i in range(12):
                p=struct.unpack_from('<I',raw,40+i*4)[0]
                if p: extents.append((i,1,p))
        data=bytearray(size)
        for logical,count,phys in extents:
            for j in range(count):
                dst=(logical+j)*self.block
                if dst>=size: break
                self.f.seek((phys+j)*self.block)
                chunk=self.f.read(min(self.block,size-dst))
                data[dst:dst+len(chunk)] = chunk
        return mode,size,bytes(data)

    def dirents(self, ino:int):
        _m,_s,data=self.read_inode(ino)
        pos=0
        while pos+8 <= len(data):
            ent_ino,rec_len,name_len,ft=struct.unpack_from('<IHBB',data,pos)
            if rec_len < 8: break
            if ent_ino:
                yield ent_ino,data[pos+8:pos+8+name_len].decode('utf-8','replace'),ft
            pos += rec_len

    def find(self,path:str):
        ino=2
        for comp in [x for x in path.split('/') if x]:
            nxt=None
            for child,name,_ft in self.dirents(ino):
                if name == comp: nxt=child; break
            if nxt is None: return None
            ino=nxt
        return ino

    def extract(self,path:str,dst:Path):
        ino=self.find(path)
        if ino is None: raise FileNotFoundError(path)
        mode,size,data=self.read_inode(ino)
        dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
        return mode,size

    def close(self): self.f.close()


@dataclass
class Part:
    name:str; path:str; flash_size:int; part_offset:int; flash_offset:int; padded_size:int; byte_count:int


def parse_rkaf(data: bytes):
    if data[:4] != RKAF: raise ValueError('embedded image is not RKAF')
    length=struct.unpack_from('<I',data,4)[0]
    model=cstr(data[8:42]); ident=cstr(data[42:72]); manufacturer=cstr(data[72:128])
    unknown,version,num_parts=struct.unpack_from('<III',data,128)
    parts=[]
    for i in range(num_parts):
        st=140+i*112; b=data[st:st+112]
        vals=struct.unpack_from('<IIIII',b,92)
        parts.append(Part(cstr(b[:32]),cstr(b[32:92]),*vals))
    return {'length':length,'model':model,'id':ident,'manufacturer':manufacturer,'version':version,'parts':parts}


def unpack_update(src: Path, out: Path):
    out.mkdir(parents=True,exist_ok=True)
    with src.open('rb') as f:
        head=f.read(0x66)
        if head[:4]!=RKFW: raise ValueError('not RKFW')
        chip=head[0x15:0x19][::-1].decode('ascii','replace')
        boot_off,boot_size=struct.unpack_from('<II',head,0x19)
        upd_off,upd_size=struct.unpack_from('<II',head,0x21)
        f.seek(upd_off); emb=f.read(upd_size)
    (out/'rkfw_header.bin').write_bytes(head)
    (out/'loader.bin').write_bytes(emb[:0])
    (out/'embedded-update.img').write_bytes(emb)
    meta={'format':'RKFW','chip':'RK'+chip,'boot_offset':boot_off,'boot_size':boot_size,'update_offset':upd_off,'update_size':upd_size}
    (out/'rkfw.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    info=parse_rkaf(emb)
    (out/'rkaf.json').write_text(json.dumps({'length':info['length'],'model':info['model'],'id':info['id'],'manufacturer':info['manufacturer'],'version':info['version'],'parts':[asdict(x) for x in info['parts']]},indent=2),encoding='utf-8')
    return meta,info


def extract_partitions(emb_path:Path,out:Path,info):
    data=emb_path.read_bytes(); container_end=len(data)-4
    offsets=sorted({p.part_offset for p in info['parts'] if p.part_offset})
    result={}
    for p in info['parts']:
        if p.path in ('SELF','RESERVED',''): continue
        bound=min([x for x in offsets if x>p.part_offset] or [container_end])
        count=p.byte_count
        if bound-p.part_offset>count:
            count += ((bound-p.part_offset-count)>>32)<<32
        doff=p.part_offset; dlen=count
        if p.name=='parameter' and data[doff:doff+4]==b'PARM':
            dlen=struct.unpack_from('<I',data,doff+4)[0]; doff+=8
        target=out/p.path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data[doff:doff+dlen])
        result[p.name]={'path':p.path,'offset':p.part_offset,'size':dlen}
    return result


def run_cmd(cmd):
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=False)
        return p.returncode,p.stdout
    except FileNotFoundError:
        return 127,''


def inspect_firmware(rootfs:Path,out:Path):
    er=Ext4Reader(rootfs)
    work=out/'firmware'; work.mkdir(parents=True,exist_ok=True)
    selected=['usr/bin/mfp.afx','usr/lib/libhal.so','usr/lib/libcommon.so','usr/lib/libevent_mgr.so','usr/lib/libosal.so','etc/hal_module_config.json','etc/gpio.json','etc/generic_power.json','etc/led.json']
    got=[]
    for p in selected:
        try:
            mode,size=er.extract(p,work/p)
            got.append({'path':p,'size':size,'mode':oct(mode)})
        except FileNotFoundError:
            got.append({'path':p,'missing':True})
    er.close()
    mfp=work/'usr/bin/mfp.afx'
    report={'files':got}
    if mfp.exists():
        blob=mfp.read_bytes()[:64]
        report['elf_magic']=blob[:4].hex(); report['elf_class']=blob[4]; report['elf_machine']=blob[18:20].hex()
        rc,outstr=run_cmd(['readelf','-l',str(mfp)])
        report['readelf_program_headers']=outstr if rc==0 else 'readelf unavailable'
        rc,outstr=run_cmd(['readelf','-d',str(mfp)])
        report['readelf_dynamic']=outstr if rc==0 else 'readelf unavailable'
        rc,syms=run_cmd(['nm','-D','--defined-only',str(work/'usr/lib/libhal.so')]) if (work/'usr/lib/libhal.so').exists() else (1,'')
        report['hal_virtual_symbols']=[ln.strip() for ln in syms.splitlines() if 'pi_hal_virt_' in ln]
        strings=run_cmd(['strings','-n','6',str(mfp)])[1]
        report['virtual_strings']=[ln for ln in strings.splitlines() if re.search(r'qemu|virtual_platform|pi_hal_virt',ln,re.I)][:120]
    config=work/'etc/hal_module_config.json'
    if config.exists():
        try:
            cfg=json.loads(config.read_text('utf-8'))['hal_module_config']
            report['hal_modules']=[x for x in cfg if x.get('module_name') in {'virtual_platform','gpio','pwm','generic_power','rtc'}]
        except Exception as e: report['config_error']=str(e)
    (out/'firmware-analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


@dataclass
class VirtualPrinter:
    paper_present:bool=False
    paper_jam:bool=False
    motor_feed:bool=False
    heater_c:float=25.0
    pages:int=0
    job_state:str='IDLE'
    sensor_1:bool=False
    sensor_2:bool=False
    events:list[str]=field(default_factory=list)

    def log(self,msg): self.events.append(msg)
    def insert_paper(self):
        self.paper_present=True; self.sensor_1=True; self.log('SENSOR1=ON (paper inserted)')
    def remove_paper(self):
        self.paper_present=False; self.sensor_1=False; self.sensor_2=False; self.log('SENSOR1=OFF (paper removed)')
    def start_job(self,pages=1):
        self.job_state='PROCESSING'; self.motor_feed=True; self.log(f'JOB_START pages={pages}')
        if not self.paper_present:
            self.job_state='STOPPED'; self.motor_feed=False; self.log('JOB_STOPPED reason=MEDIA_NEEDED'); return
        if self.paper_jam:
            self.job_state='STOPPED'; self.motor_feed=False; self.log('JOB_STOPPED reason=PAPER_JAM'); return
        self.sensor_2=True; self.pages += pages; self.log('SENSOR2=ON'); self.motor_feed=False; self.job_state='COMPLETED'; self.log(f'JOB_COMPLETED pages={pages}')
    def jam(self):
        self.paper_jam=True; self.log('FAULT=paper_jam')
    def clear_jam(self):
        self.paper_jam=False; self.log('FAULT_CLEARED=paper_jam')


def demo(out:Path):
    v=VirtualPrinter();
    v.log('BOOT'); v.log('VIRTUAL_HAL=READY'); v.log('PRINTER_STATE=IDLE')
    v.insert_paper(); v.start_job(1)
    first=list(v.events)
    v2=VirtualPrinter(); v2.log('BOOT'); v2.log('VIRTUAL_HAL=READY'); v2.insert_paper(); v2.jam(); v2.start_job(1); v2.clear_jam(); v2.paper_jam=False; v2.start_job(1)
    payload={'normal':{'pass':v.job_state=='COMPLETED','pages':v.pages,'events':first},'paper_jam_recovery':{'pass':v2.job_state=='COMPLETED','pages':v2.pages,'events':v2.events}}
    (out/'demo-result.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    return payload


def main():
    ap=argparse.ArgumentParser(description='RK3588 Printer Simulation PoC')
    sp=ap.add_subparsers(dest='cmd',required=True)
    a=sp.add_parser('inspect'); a.add_argument('firmware'); a.add_argument('-o','--out',default='poc-out')
    d=sp.add_parser('demo'); d.add_argument('-o','--out',default='poc-out')
    x=sp.add_parser('all'); x.add_argument('firmware'); x.add_argument('-o','--out',default='poc-out')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    if args.cmd in ('inspect','all'):
        fw=Path(args.firmware)
        meta,info=unpack_update(fw,out/'package')
        parts=extract_partitions(out/'package/embedded-update.img',out/'package/Image',info)
        rootfs=out/'package/Image/rootfs.ext4'
        report=inspect_firmware(rootfs,out) if rootfs.exists() else {'error':'rootfs.ext4 not extracted'}
        summary={'rkfw':meta,'rkaf':{'model':info['model'],'manufacturer':info['manufacturer'],'parts':[asdict(x) for x in info['parts']]},'extracted':parts,'analysis':report}
        (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(summary,indent=2,ensure_ascii=False))
    if args.cmd in ('demo','all'):
        print(json.dumps(demo(out),indent=2,ensure_ascii=False))

if __name__=='__main__': main()
