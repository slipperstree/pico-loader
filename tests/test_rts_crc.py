"""Execute actual built CRC functions; optional previous ELF is a baseline.
Instruction counts compare the algorithm only, not physical console timing.
"""
import json,os,random,struct,subprocess,sys,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
def execute(elf,data,initial):
    symbols={}
    for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
        p=line.split()
        if len(p)==3:symbols[p[2]]=int(p[0],16)
    entry=next(v for k,v in symbols.items() if k.startswith('crc.constprop.'))
    raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x02000000,0x400000)
    for n in range(phnum):
        kind,offset,addr,pa,filesize,memsize,flags,align=struct.unpack_from('<8I',raw,phoff+n*phsize)
        if kind==1 and filesize:u.mem_write(addr,raw[offset:offset+filesize])
    done=0x020f0000;u.mem_write(0x02040000,data)
    state={'done':False,'instructions':0}
    def code(uc,addr,size,user):
        if addr==done:state['done']=True;uc.emu_stop()
        else:state['instructions']+=1
    u.hook_add(UC_HOOK_CODE,code)
    u.reg_write(UC_ARM_REG_R0,initial);u.reg_write(UC_ARM_REG_R1,0x02040000)
    u.reg_write(UC_ARM_REG_R2,128);u.reg_write(UC_ARM_REG_SP,0x023ff000);u.reg_write(UC_ARM_REG_LR,done)
    u.emu_start(entry,0,count=100000)
    assert state['done'] and u.reg_read(UC_ARM_REG_SP)==0x023ff000
    expected=zlib.crc32(data,initial^0xffffffff)^0xffffffff
    assert u.reg_read(UC_ARM_REG_R0)==expected
    return state['instructions']
current=root/'build/rts-worker/worker.elf';rng=random.Random(125)
vectors=[(bytes(512),0xffffffff),(bytes([255])*512,0xffffffff),(bytes(rng.randrange(256) for _ in range(512)),0x12345678)]
new=[execute(current,data,initial) for data,initial in vectors]
report={'new_instructions_per_512_bytes':new,'hardware_speed':'not measured'}
if len(sys.argv)>2:
    old=[execute(Path(sys.argv[2]),data,initial) for data,initial in vectors]
    assert all(n<o for n,o in zip(new,old))
    report['old_instructions_per_512_bytes']=old
    report['instruction_reduction_percent']=round(100*(1-new[0]/old[0]),1)
(root/'build/rts-worker/crc-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS actual CRC matches zlib on zero, FF and seeded data; '+json.dumps(report))
