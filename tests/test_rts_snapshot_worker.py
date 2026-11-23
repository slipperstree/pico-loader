"""Execute the actual relocated worker against a modeled DSPico sector device.
Cache/MPU operations are recorded, not hardware-emulated. Never accesses a disk.
"""
import json,os,re,struct,subprocess,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'rts/pydeps'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
args=[a for a in sys.argv[1:] if a!='--zero-ready-only']
root=Path(args[0]) if args else Path(__file__).resolve().parents[1]
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
folder=root/'build/rts-worker'
meta=json.loads((folder/'RtsM2Image.json').read_text())
original=(folder/'worker.bin').read_bytes()
symbols={}
for line in subprocess.check_output([prefix+'nm',str(folder/'worker.elf')],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
coprocessor=[]
for line in subprocess.check_output([prefix+'objdump','-d',str(folder/'worker.elf')],text=True).splitlines():
    if re.search(r'\b(mrc|mcr)\b',line):coprocessor.append(int(line.split(':')[0].strip(),16)-meta['link_base'])
MAGIC,VERSION,GAME=0x324d5452,0x20001,0x4a473241
PAYLOAD=0x40c000
SECTORS=1+PAYLOAD//512
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
      UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
      UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
EXTENTS=[(2048,0x1000),(4096,0x3000),(SECTORS-6144,0x6000)]
ALLOWED=[first+i for count,first in EXTENTS for i in range(count)]

def run_case(label,base=0x023fa000,badmap=False,busy=False,foreign=False,corrupt=False,timeout=False,zero_ready=False,display_capture=False,arm7_reason=0,owner7=False,settle_dma=False):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for addr,size in [(0x01ff8000,0x8000),(0x02000000,0x400000),(0x027c0000,0x4000),(0x06840000,0x20000),
                      (0x04000000,0x2000),(0x04100000,0x1000)]:u.mem_map(addr,size)
    main=bytes(range(256))*16384
    itcm=bytes(reversed(range(256)))*128
    u.mem_write(0x02000000,main);u.mem_write(0x01ff8000,itcm)
    u.mem_write(0x027c0000,b'\x5a'*0x4000)
    video=bytes(range(256))*512
    u.mem_write(0x06840000,video)
    u.mem_write(0x04000000,struct.pack('<I',0x00110800))
    u.mem_write(0x0400006c,struct.pack('<H',0x8008))
    u.mem_write(0x04000242,b'\x84')
    image=bytearray(original)
    for offset in meta['relocations']:
        value=struct.unpack_from('<I',image,offset)[0]
        struct.pack_into('<I',image,offset,value+base-meta['link_base'])
    workbytes=meta['memory_bytes']
    stack_start=base+symbols['gRtsM2Stack']-meta['link_base']
    assert workbytes<=0x2000,workbytes
    u.mem_write(base,b'\0'*workbytes);u.mem_write(base,bytes(image))
    words=[MAGIC,VERSION,SECTORS,len(EXTENTS),0x800,0x10000,GAME,arm7_reason]
    for count,first in EXTENTS:words.extend((count,first))
    words += [0]*(72-len(words))
    if badmap:words[9]=0x400 # point into FAT metadata: must be rejected
    cfg=base+meta['config_offset']
    u.mem_write(cfg,struct.pack('<72I',*words)+struct.pack('<II',base,workbytes))
    prepared=bytearray(512)
    struct.pack_into('<4I',prepared,0,MAGIC,VERSION,PAYLOAD+512,GAME)
    struct.pack_into('<I',prepared,20,PAYLOAD)
    if foreign:prepared[0]^=1
    disk={ALLOWED[0]:bytes(prepared)}
    done=0x020f0000
    u.mem_write(done,b'\x70\x47')
    original_regs=[0x11110000+i for i in range(13)]
    original_regs[12]=0x023e0021
    sp=0x027c3d00
    frame=[0x4003,0x8002,0x400b,0x000000df,0xa000001f,0x11110003,
           0x88880000,0x88880001,0x88880002,0x88880003,0x8888000c,0x02001235]
    u.mem_write(sp,struct.pack('<12I',*frame))
    u.reg_write(UC_ARM_REG_CPSR,0xdf)
    u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done|1)
    for reg,value in zip(REGS,original_regs):u.reg_write(reg,value)
    u.mem_write(0x04000204,struct.pack('<H',0x800 if owner7 else 0))
    u.mem_write(0x040001a0,struct.pack('<H',0x8000))
    if display_capture:u.mem_write(0x04000064,struct.pack('<I',0x80000000))
    if busy or settle_dma:u.mem_write(0x040000b8,struct.pack('<I',0x80000000))
    expected=bytearray(u.mem_read(0x02000000,0x400000))
    expected[base-0x02000000:base-0x02000000+workbytes]=b'\0'*workbytes
    state={'mode':'idle','word':0,'sector':0,'read_sector':0,'peer':12,'own':10,
           'writes':[],'commands':0,'fault':None,'done':False,'header_phases':[],'cache_ops':0,'vcount':192,'frames':0,'stages':[],'brightness':[]}
    if settle_dma and not foreign:raise AssertionError('Use foreign guard to test settling without a second full dump')
    control=0x0005707d
    cp={(1,0,0):control,(9,1,0):0x027c000a,(9,1,1):0x20}
    def coproc(uc,addr,size,data):
        ins=struct.unpack('<I',uc.mem_read(addr,4))[0]
        crn,crm,opc2,rd=(ins>>16)&15,ins&15,(ins>>5)&7,(ins>>12)&15
        if ins&(1<<20):uc.reg_write(REGS[rd],cp[(crn,crm,opc2)])
        elif crn==1:cp[(1,0,0)]=uc.reg_read(REGS[rd])
        elif crn==7:state['cache_ops']+=1
        else:raise AssertionError(('Unexpected CP15',hex(ins)))
        uc.reg_write(UC_ARM_REG_PC,addr+4)
    for offset in coprocessor:u.hook_add(UC_HOOK_CODE,coproc,begin=base+offset,end=base+offset)
    def stopped(uc,addr,size,data):
        if addr==done:state['done']=True
        else:state['fault']=uc.reg_read(UC_ARM_REG_R0)
        uc.emu_stop()
    u.hook_add(UC_HOOK_CODE,stopped,begin=done,end=done)
    def stage_call(uc,addr,size,data):state['stages'].append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
    progress_address=base+symbols['progress']-meta['link_base']
    u.hook_add(UC_HOOK_CODE,stage_call,begin=progress_address,end=progress_address)
    fault=base+symbols['fault']-meta['link_base']
    u.hook_add(UC_HOOK_CODE,stopped,begin=fault,end=fault)
    def read(uc,access,addr,size,value,data):
        if addr==0x04000006:
            previous=state['vcount'];state['vcount']=(previous+17)%263
            if state['vcount']<previous:state['frames']+=1
            uc.mem_write(addr,struct.pack('<H',state['vcount']))
        elif addr==0x040000b8 and settle_dma and state['frames']>=1:
            uc.mem_write(addr,struct.pack('<I',0))
        if addr==0x04000180:
            uc.mem_write(addr,struct.pack('<H',0x4000|(state['own']<<8)|state['peer']))
        elif addr==0x040001a4:
            active=state['mode'] in ('write','poll','read')
            value=0x80800000 if active else 0
            if timeout and state['mode']=='poll':value=0x80000000
            uc.mem_write(addr,struct.pack('<I',value))
        elif addr==0x04100010:
            if state['mode']=='poll':value=0 if zero_ready else 1;state['mode']='idle'
            else:
                assert state['mode']=='read',state
                blob=disk.get(state['read_sector'],b'\0'*512)
                value=struct.unpack_from('<I',blob,state['word']*4)[0]
                if corrupt and state['read_sector']==ALLOWED[2] and state['word']==0:value^=1
                state['word']+=1
                if state['word']==128:state['mode']='idle'
            uc.mem_write(addr,struct.pack('<I',value))
    u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100013)
    def write(uc,access,addr,size,value,data):
        if 0x02000000<=addr<0x02400000:
            assert base<=addr and addr+size<=base+workbytes,('Game RAM modified',hex(addr))
            current_sp=uc.reg_read(UC_ARM_REG_SP)
            if base<=current_sp<base+workbytes:assert stack_start<=current_sp<=stack_start+1024,('Worker stack escaped',hex(current_sp))
            assert stack_start<=addr and addr+size<=stack_start+1024 or cfg<=addr or base+symbols['ioBudget']-meta['link_base']<=addr<base+symbols['ioBudget']-meta['link_base']+4,('Worker code overwritten / stack overflow',hex(addr))
        elif addr in (0x0400006c,0x0400106c):
            state['brightness'].append((addr,value))
        elif addr==0x04000180:
            state['own']=(value>>8)&15
            assert value&0x4000,'IPCSYNC IRQ control lost'
            if state['own']==13:state['peer']=0
        elif addr==0x040001a4 and value&0x80000000:
            cmd=bytes(uc.mem_read(0x040001a8,8));op=cmd[0]
            argument=int.from_bytes(cmd[4:],'big')
            state['commands']+=1
            if op==0xe3:
                assert argument in ALLOWED
                state['read_sector']=argument;state['mode']='idle'
            elif op==0xe4:state['mode']='poll'
            elif op==0xe5:state['mode']='read';state['word']=0
            elif op==0xf6:
                assert cmd[:4]==bytes.fromhex('f6e10d9b')
                assert argument in ALLOWED,('Write outside allocated file',hex(argument))
                state['sector']=argument;state['word']=0;state['buffer']=bytearray();state['mode']='write'
            else:raise AssertionError(('Unknown card command',cmd.hex()))
        elif addr==0x04100010:
            assert state['mode']=='write',state
            state['buffer']+=struct.pack('<I',value)
            state['word']+=1
            if state['word']==128:
                disk[state['sector']]=bytes(state['buffer']);state['writes'].append(state['sector']);state['mode']='idle'
                if state['sector']==ALLOWED[0]:state['header_phases'].append(struct.unpack_from('<I',state['buffer'],16)[0])
    u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x02000000,end=0x04100013)
    u.emu_start(base+meta['entry_offset'],0,count=1500000000)
    if badmap or busy or display_capture or arm7_reason or owner7:
        assert state['done'] and not state['writes'] and not state['commands'],state
        if owner7:assert (8,2) in state['stages']
        if badmap:assert (8,256) in state['stages']
        if busy or display_capture or arm7_reason:
            assert state['brightness'].count((0x0400006c,0x400c))==3
            assert state['brightness'].count((0x0400106c,0x400c))==3
            assert not state['stages'], 'Unsafe VRAM remap during DMA/capture refusal'
        else:assert state['frames']>=180, 'S8 feedback was not held long enough'
        assert bytes(u.mem_read(0x06840000,0x20000))==video
        assert struct.unpack('<I',u.mem_read(0x04000000,4))[0]==0x00110800
        assert bytes(u.mem_read(0x04000242,1))==b'\x84'
        assert struct.unpack('<H',u.mem_read(0x0400006c,2))[0]==0x8008
        assert [u.reg_read(reg) for reg in REGS]==original_regs
        assert u.reg_read(UC_ARM_REG_SP)==sp
    elif foreign or corrupt or timeout or zero_ready:
        assert state['fault']==(2 if foreign else 6 if corrupt else 1),state
        assert not state['done'] and 2 not in state['header_phases']
        if foreign or timeout or zero_ready:assert not state['writes']
        if zero_ready:assert state['commands']<=4098
    else:
        assert state['done'] and state['fault'] is None,state
        assert state['header_phases']==[1,2],state['header_phases']
        blob=b''.join(disk[s] for s in ALLOWED)
        header=struct.unpack('<128I',blob[:512])
        assert header[4]==2 and header[6]==header[17]==zlib.crc32(blob[512:])
        assert blob[512:512+0x400000]==expected
        assert blob[-0x8000:]==itcm
        assert header[20:24]==tuple(frame[6:10])
        assert header[24:32]==tuple(original_regs[4:12])
        assert header[33]==sp+48 and header[36]==frame[4] and header[38]==0x023e0021
        assert [u.reg_read(reg) for reg in REGS]==original_regs
        assert u.reg_read(UC_ARM_REG_SP)==sp and u.reg_read(UC_ARM_REG_LR)==done|1
        assert cp[(1,0,0)]==control and state['cache_ops']>=257
        assert bytes(u.mem_read(0x06840000,0x20000))==video, 'VRAM progress line not restored'
        assert struct.unpack('<I',u.mem_read(0x04000000,4))[0]==0x00110800
        assert bytes(u.mem_read(0x04000242,1))==b'\x84'
        assert struct.unpack('<H',u.mem_read(0x0400006c,2))[0]==0x8008
        (folder/'model-snapshot.bin').write_bytes(blob)
    print('PASS',label,'commands',state['commands'],'file-sector writes',len(state['writes']),flush=True)

if '--zero-ready-only' not in sys.argv:
    run_case('complete 4 MiB + DTCM + ITCM capture and full readback CRC')
    run_case('alternate relocation address',base=0x023e0000)
    run_case('invalid mapping refuses all SD commands',badmap=True)
    run_case('DMA precheck refuses all SD commands',busy=True)
    run_case('foreign file is never overwritten',foreign=True)
    run_case('corrupt readback never commits completion',corrupt=True)
    run_case('transport timeout fails closed without any write',timeout=True)
    print('Actual SD timing, cache coherency, MPU/TCM mappings and console hardware remain unvalidated.')
run_case('continuous SD-not-ready response terminates within shared retry budget',zero_ready=True)
run_case('active display capture declines without SD access',display_capture=True)
run_case('ARM7 DMA refusal never issues SD commands',arm7_reason=512)
run_case('ARM7 sound capture refusal never issues SD commands',arm7_reason=1024)
run_case('card owner refusal displays S8 reason',owner7=True)
run_case('one-shot DMA settles before first SD command',settle_dma=True,foreign=True)
