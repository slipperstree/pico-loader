"""Execute actual progress drawing; protect every pixel outside its backup strip."""
import json,os,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'rts/pydeps'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
folder=root/'build/rts-worker';meta=json.loads((folder/'RtsM2Image.json').read_text());blob=bytearray((folder/'worker.bin').read_bytes())
symbols={}
for line in subprocess.check_output([prefix+'nm',str(folder/'worker.elf')],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
base=0x023fa000
for offset in meta['relocations']:
    value=struct.unpack_from('<I',blob,offset)[0];struct.pack_into('<I',blob,offset,value+base-meta['link_base'])
for stage,value in ((1,0),(3,0),(5,1234),(6,8256),(8,2),(9,4)):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x02000000,0x400000);u.mem_map(0x06840000,0x20000)
    u.mem_write(base,b'\0'*meta['memory_bytes']);u.mem_write(base,bytes(blob))
    original=bytes([0x6a])*0x20000;u.mem_write(0x06840000,original)
    done=0x020f0000;u.mem_write(done,b'\x70\x47');state={'done':False,'writes':0}
    def stop(uc,addr,size,data):state['done']=True;uc.emu_stop()
    def write(uc,access,addr,size,value,data):
        pixel=(addr-0x06840000)//2;assert size==2 and pixel//256<8 and pixel%256<96,(hex(addr),size)
        state['writes']+=1
    u.hook_add(UC_HOOK_CODE,stop,begin=done,end=done)
    u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x06840000,end=0x0685ffff)
    stack=base+symbols['gRtsM2Stack']-meta['link_base']+1024
    u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,done|1)
    u.reg_write(UC_ARM_REG_R0,stage);u.reg_write(UC_ARM_REG_R1,value)
    u.emu_start(base+symbols['progress']-meta['link_base'],0,count=1000000)
    assert state['done'] and state['writes']>768 and u.reg_read(UC_ARM_REG_SP)==stack
    screen=bytes(u.mem_read(0x06840000,0x20000));white=0
    for y in range(8):
        for x in range(96):white+=screen[(y*256+x)*2:(y*256+x)*2+2]==b'\xff\xff'
    assert white>50
    if stage==8:
        # A readable B acknowledgement replaces the irrelevant payload total.
        for x,bits in enumerate((0x7f,0x49,0x49,0x49,0x36)):
            for y in range(7):
                pos=(y*256+11*6+x)*2
                assert screen[pos:pos+2]==(b'\xff\xff' if bits&(1<<y) else b'\x00\x80')
    print('PASS actual progress stage',stage,'value',value,'white pixels',white,'all writes within 96x8 saved strip')
