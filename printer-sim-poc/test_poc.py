import json
from pathlib import Path
from poc import VirtualPrinter, parse_rkaf

def test_virtual_printer_normal():
    v=VirtualPrinter(); v.insert_paper(); v.start_job(2)
    assert v.job_state=='COMPLETED'
    assert v.pages==2

def test_virtual_printer_jam_recovery():
    v=VirtualPrinter(); v.insert_paper(); v.jam(); v.start_job(1)
    assert v.job_state=='STOPPED'
    v.clear_jam(); v.start_job(1)
    assert v.job_state=='COMPLETED'

def test_rkaf_header():
    b=bytearray(2048); b[:4]=b'RKAF'; b[8:14]=b'RK3588'; b[136:140]=(1).to_bytes(4,'little')
    # minimal parser only needs header and one zeroed part
    info=parse_rkaf(bytes(b))
    assert info['model']=='RK3588'
    assert len(info['parts'])==1
