"""Run the real compiled prompt and font renderer; reject any game-RAM writes."""
import os,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'pydeps'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
elf=root/'build/picoLoader9_DSPICO_rts_probe.elf'
data=elf.read_bytes()
symbols={}
for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
phoff=struct.unpack_from('<I',data,28)[0]
phsize,phnum=struct.unpack_from('<HH',data,42)
segments=[]
for n in range(phnum):
    kind,offset,vaddr,paddr,filesize,memsize,flags,align=struct.unpack_from('<8I',data,phoff+n*phsize)
    if kind==1:segments.append((vaddr,data[offset:offset+filesize]))
for already_unpacked in (False,True):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for base,size in [(0x01000000,0x10000),(0x02000000,0x400000),(0x04000000,0x2000),
                      (0x05000000,0x1000),(0x06000000,0x100000),(0x06800000,0x100000),(0x07800000,0x4000)]:
        u.mem_map(base,size)
    for addr,blob in segments:u.mem_write(addr,blob)
    font=symbols['font_nft2']
    if already_unpacked:
        for offset in (4,8,12):
            value=struct.unpack('<I',u.mem_read(font+offset,4))[0]
            u.mem_write(font+offset,struct.pack('<I',font+value))
    before=bytes(u.mem_read(font,24))
    message=b'RTS research: CPU probe M1\nNOT save/load states yet.\nHold L+R+Down+Select.\nDim/pause about 3 seconds,\nthen continue automatically.\0'
    u.mem_write(0x022f0000,message)
    done=0x020f0000
    u.mem_write(done,b'\x70\x47')
    state={'vcount':0,'keys':0,'done':False,'pixels':False,'lowest_stack':0x07802f00}
    def read(uc,access,addr,size,value,userdata):
        if addr==0x04000006:
            state['vcount']+=1
            uc.mem_write(addr,struct.pack('<H',191 if state['vcount']%2 else 192))
        elif addr==0x04000130:
            state['keys']+=1
            uc.mem_write(addr,struct.pack('<H',0x3ff if state['keys']==1 else 0x3fe))
    def write(uc,access,addr,size,value,userdata):
        assert not (0x02000000<=addr<0x02400000),hex(addr)
        if 0x06000000<=addr<0x0600c000 and value:state['pixels']=True
        if 0x07800000<=addr<0x07804000:state['lowest_stack']=min(state['lowest_stack'],addr)
    def code(uc,addr,size,userdata):
        if addr==done:state['done']=True;uc.emu_stop()
    u.hook_add(UC_HOOK_MEM_READ,read)
    u.hook_add(UC_HOOK_MEM_WRITE,write)
    u.hook_add(UC_HOOK_CODE,code)
    u.reg_write(UC_ARM_REG_CPSR,0x1f)
    u.reg_write(UC_ARM_REG_SP,0x07802f00)
    u.reg_write(UC_ARM_REG_LR,done|1)
    u.reg_write(UC_ARM_REG_R0,0x022f0000)
    u.emu_start(symbols['rtsProbeMessage']|1,0,count=2000000)
    assert state['done'] and state['pixels'],state
    assert bytes(u.mem_read(font,24))==before
    assert state['lowest_stack']>=0x07801000,state
    print('PASS real prompt: no game-RAM writes, glyph pixels rendered, local font header, bounded DTCM stack; pre-unpacked=',already_unpacked)
print('Real VRAM bank aliases, scanout, button timing and hardware are not simulated.')
