"""Run actual Thumb SD wrappers; check full-call busy lifetime and ABI."""
import os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
elf=root/'build/picoLoader9_DSPICO_snapshot_m2.elf'
symbols={}
for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
scratch=root/'build/rts-io-guard-test';scratch.mkdir(exist_ok=True)
for section,function in [('dspico_readsdsectors','dspico_readSdSectors'),('dspico_writesdsectors','dspico_writeSdSectors')]:
    path=scratch/(section+'.bin')
    subprocess.run([prefix+'objcopy','--dump-section',section+'='+str(path),str(elf)],check=True)
    base=0x03801000;origin=symbols['__start_'+section]
    at=lambda name:base+(symbols[name]&~1)-origin
    busy=at(section+'_busy');body=at(function+'Body');done=0x0380f000;sp=0x0380e000
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x03800000,0x10000);u.mem_write(base,path.read_bytes())
    inputs=[123,0x02008000,3];state={'calls':0,'done':False,'busy_writes':[]}
    for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2],inputs):u.reg_write(reg,value)
    u.reg_write(UC_ARM_REG_R4,0x77774444);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done|1)
    def code(uc,addr,size,data):
        if addr==body:
            assert struct.unpack('<I',uc.mem_read(busy,4))[0]==1
            assert [uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]]==inputs
            state['calls']+=1;uc.reg_write(UC_ARM_REG_R0,0x11223344)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        elif addr==done:state['done']=True;uc.emu_stop()
    def write(uc,access,addr,size,value,data):
        if addr==busy:state['busy_writes'].append(value)
        else:assert sp-32<=addr<sp,('Write escaped wrapper stack',hex(addr))
    u.hook_add(UC_HOOK_CODE,code)
    u.hook_add(UC_HOOK_MEM_WRITE,write)
    u.emu_start(at(function)|1,0,count=1000)
    assert state=={'calls':1,'done':True,'busy_writes':[1,0]},state
    assert struct.unpack('<I',u.mem_read(busy,4))[0]==0
    assert u.reg_read(UC_ARM_REG_SP)==sp and u.reg_read(UC_ARM_REG_R4)==0x77774444
    assert u.reg_read(UC_ARM_REG_R0)==0x11223344
    print('PASS actual SD busy wrapper',function,'sets before body, clears after full return; args/stack/r4 preserved')
