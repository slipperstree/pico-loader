"""Exercise actual sector functions with ready delays and CPU-speed-independent clocks.
Optional second argument: old ELF, to reproduce its 4096-poll rejection.
No physical device or filesystem image is accessed.
"""
import json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
legacy=len(sys.argv)>2
elf=Path(sys.argv[2]) if legacy else root/'build/rts-worker/worker.elf'
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
symbols={}
for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
def run(write=True,delay=0,polls_per_frame=64,stall=None,frozen=False,ready_frame=None):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for addr,size in [(0x02000000,0x400000),(0x04000000,0x2000),(0x04100000,0x1000)]:u.mem_map(addr,size)
    for n in range(phnum):
        kind,offset,addr,pa,filesize,memsize,flags,align=struct.unpack_from('<8I',raw,phoff+n*phsize)
        if kind==1 and filesize:u.mem_write(addr,raw[offset:offset+filesize])
    cfg=symbols['gRtsM2'];clock=symbols['gRtsM2Frames'];done=0x020f0000;buffer=0x02080000
    words=[0x324d5452,0x20001,8289,1,0x800,0x10000,0x4a473241,0,8289,0x1000]+[0]*62
    u.mem_write(cfg,struct.pack('<72I',*words));data=bytes(range(256))*2;u.mem_write(buffer,data)
    u.mem_write(0x04000180,struct.pack('<H',0x4a0c))
    state={'done':False,'mode':'idle','polls':0,'status':0,'remaining':delay,'word':0,'bytes':bytearray(),'commands':[],'heartbeats':[]}
    def frame():return 0 if frozen else state['polls']//polls_per_frame
    def read(uc,access,addr,size,value,user):
        if addr==clock:uc.mem_write(clock,struct.pack('<I',frame()))
        elif addr==0x040001a4:
            state['polls']+=1;mode=state['mode'];value=0
            if mode in ('write','read','poll'):value=0x80800000
            if (stall=='data' and mode=='write') or (stall=='status_data' and mode=='poll'):value=0x80000000
            if mode=='data_end' or mode=='status_end':value=0x80000000
            uc.mem_write(addr,struct.pack('<I',value))
        elif addr==0x04100010:
            if state['mode']=='poll':
                state['status']+=1
                ready=frame()>=ready_frame if ready_frame is not None else state['remaining']==0
                if state['remaining'] is not None and state['remaining']>0:state['remaining']-=1
                if ready:state['ready_at']=frame()
                value=int(ready);state['mode']='status_end' if stall=='status_end' else 'idle'
            else:
                assert state['mode']=='read'
                value=struct.unpack_from('<I',data,state['word']*4)[0];state['word']+=1
                if state['word']==128:state['mode']='idle'
            uc.mem_write(addr,struct.pack('<I',value))
    def write_hook(uc,access,addr,size,value,user):
        if addr==0x040001a4 and value&0x80000000:
            cmd=bytes(uc.mem_read(0x040001a8,8));op=cmd[0];state['commands'].append(op)
            if op in (0xe3,0xf6):assert int.from_bytes(cmd[4:],'big')==0x1001
            if op==0xf6:state['mode']='write';state['word']=0
            elif op==0xe3:state['mode']='idle'
            elif op==0xe4:state['mode']='poll'
            elif op==0xe5:state['mode']='read';state['word']=0
            else:raise AssertionError(cmd.hex())
        elif addr==0x04100010:
            assert state['mode']=='write'
            state['bytes']+=struct.pack('<I',value);state['word']+=1
            if state['word']==128:state['mode']='data_end' if stall=='data_end' else 'idle'
        elif addr==0x04000180:
            assert value&0x4000;state['heartbeats'].append((value>>8)&15)
    def code(uc,addr,size,user):
        if addr==done:state['done']=True;uc.emu_stop()
    u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write_hook);u.hook_add(UC_HOOK_CODE,code,begin=done,end=done)
    name=next(k for k in symbols if k.startswith('writeSector' if write else 'readSector'))
    u.reg_write(UC_ARM_REG_SP,0x023ff000);u.reg_write(UC_ARM_REG_LR,done)
    u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_R1,buffer)
    u.emu_start(symbols[name],0,count=150000000)
    assert state['done'] and u.reg_read(UC_ARM_REG_SP)==0x023ff000
    ok=u.reg_read(UC_ARM_REG_R0)
    if ok:
        if write:assert bytes(state['bytes'])==data
        else:assert bytes(u.mem_read(cfg+808,512))==data
    detail=None
    if not legacy:detail=struct.unpack('<5I',u.mem_read(symbols['ioState'],20))
    return {'ok':ok,'ready_at':state.get('ready_at'),'frames':frame(),'status_polls':state['status'],'polls':state['polls'],'detail':detail,
            'write_commands':state['commands'].count(0xf6),'heartbeat_changes':len(set(state['heartbeats']))}

reports=[]
for rate in (64,256):
    for write in (True,False):
        r=run(write=write,delay=5000,polls_per_frame=rate);reports.append(r)
        if legacy:
            assert not r['ok'] and r['status_polls']==4096 and r['frames']<180,r
        else:
            assert r['ok'] and r['status_polls']==5001 and r['frames']<180,r
            assert r['heartbeat_changes']==2,r
print('PASS',('reproduced old early rejection' if legacy else '5000-poll delayed ready succeeds at two CPU/poll speeds'),reports)
if not legacy:
    for rate in (64,256):
        for write in (True,False):
            r=run(write=write,polls_per_frame=rate,ready_frame=100)
            assert r['ok'] and r['ready_at']==100 and 100<=r['frames']<=103,r
        r=run(delay=None,polls_per_frame=rate)
        assert not r['ok'] and r['frames']==180 and r['detail'][4]==6,r
        print('PASS same physical readiness/deadline at CPU poll rate',rate)
    for stall,reason in [(None,6),('data',2),('data_end',3),('status_data',4),('status_end',5)]:
        r=run(delay=None if stall is None else 0,stall=stall)
        assert not r['ok'] and r['detail'][4]==reason and 180<=r['frames']<184,r
        assert r['write_commands']==1 and r['heartbeat_changes']==2,r
        print('PASS frame deadline',stall or 'SD not ready',r)
    r=run(stall='data',frozen=True)
    assert not r['ok'] and r['detail'][4]==7 and r['frames']==0,r
    print('PASS stopped clock hits finite fallback',r)
out=root/'build/rts-worker'/('transport-legacy.json' if legacy else 'transport-report.json')
out.write_text(json.dumps({'legacy':legacy,'delayed_ready':reports},indent=2),encoding='utf-8')
