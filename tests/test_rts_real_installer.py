"""Execute real ARM9Patcher/allocator/installer on the user's ROM, without I/O."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys
sys.path.insert(0,str(Path(__file__).parent/'pydeps'))
from ndspy.rom import NintendoDSRom
from ndspy import codeCompression
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
full='--full' in sys.argv
root=Path(sys.argv[1]);rompath=Path(sys.argv[2]);P4='--p4' in sys.argv;M32='--m32' in sys.argv or P4;M3='--m3' in sys.argv or M32;elf=root/('build/picoLoader9_DSPICO_restore_p4.elf' if P4 else 'build/picoLoader9_DSPICO_capture_m32.elf' if M32 else 'build/picoLoader9_DSPICO_capture_m3.elf' if M3 else 'build/picoLoader9_DSPICO_snapshot_m2.elf')
# This optional integration test uses a separately supplied, exact A2GJ image.
# No ROM data or extracted game code is written into the repository.
assert hashlib.sha256(rompath.read_bytes()).hexdigest()=='85e0e265a9d855a5d156a09794571b93fb13eab616814d5df49e9fcec01277fb', 'Unexpected test ROM'
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
symbols={}
for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for base,size in [(0x01000000,0x10000),(0x02000000,0x1000000),(0x03800000,0x100000),(0x04000000,0x1000000),(0x05000000,0x1000),(0x06800000,0x100000),(0x07800000,0x4000)]:u.mem_map(base,size)
for n in range(phnum):
    kind,offset,addr,pa,filesize,memsize,flags,align=struct.unpack_from('<8I',raw,phoff+n*phsize)
    if kind==1 and filesize:u.mem_write(addr,raw[offset:offset+filesize])
rom=NintendoDSRom.fromFile(str(rompath));a9=codeCompression.decompress(rom.arm9)
u.mem_write(rom.arm9RamAddress,bytes(a9))
header=rompath.read_bytes()[:0x170]
u.mem_write(0x02fffe00,header)
u.mem_write(0x02fff800,struct.pack('<III',5,0x1000,31)+struct.pack('<4I',4,65536,2,0))
done=0x07803f00;u.mem_write(done,b'\x70\x47')
state={'done':False,'allocations':[],'requests':[],'warnings':[],'research':False}
def cstring(addr):
    out=bytearray()
    for n in range(300):
        b=bytes(u.mem_read(addr+n,1))
        if b==b'\0':break
        out+=b
    return out.decode('utf-8','replace')
def skip(uc,addr,size,data):uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
def log(uc,addr,size,data):
    level=uc.reg_read(UC_ARM_REG_R1);fmt=cstring(uc.reg_read(UC_ARM_REG_R2));arg=uc.reg_read(UC_ARM_REG_R3)
    if fmt.startswith('Allocated '):
        amount=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4))[0]
        state['allocations'].append((hex(arg),amount,state['research']))
    if level==1:raise AssertionError(('Fatal log',fmt,hex(arg)))
    skip(uc,addr,size,data)
u.hook_add(UC_HOOK_CODE,log,begin=symbols['_ZN7ILogger3LogE8LogLevelPKcz'],end=symbols['_ZN7ILogger3LogE8LogLevelPKcz'])
def error(uc,addr,size,data):raise AssertionError(('Loader error',cstring(uc.reg_read(UC_ARM_REG_R1))))
u.hook_add(UC_HOOK_CODE,error,begin=symbols['_ZN12ErrorDisplay5PrintEPKcb'],end=symbols['_ZN12ErrorDisplay5PrintEPKcb'])
for name in ('dc_flushAll','dc_drainWriteBuffer','ic_invalidateAll','dc_invalidateAll'):
    if name in symbols:u.hook_add(UC_HOOK_CODE,skip,begin=symbols[name],end=symbols[name])
def enter(uc,addr,size,data):state['research']=True
installer=next(v for k,v in symbols.items() if k.startswith('_Z19InstallRtsProbeArm9'))
u.hook_add(UC_HOOK_CODE,enter,begin=installer,end=installer)
def request(uc,addr,size,data):state['requests'].append((uc.reg_read(UC_ARM_REG_R1),state['research']))
u.hook_add(UC_HOOK_CODE,request,begin=symbols['_ZN9PatchHeap8TryAllocEm'],end=symbols['_ZN9PatchHeap8TryAllocEm'])
def finish(uc,addr,size,data):state['done']=True;uc.emu_stop()
u.hook_add(UC_HOOK_CODE,finish,begin=done,end=done)
def call(addr,args):
    state['done']=False;sp=0x07802e00
    u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done|1)
    for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args[:4]):u.reg_write(r,v)
    for i,v in enumerate(args[4:]):u.mem_write(sp+i*4,struct.pack('<I',v))
    u.emu_start(addr|1,0,count=20000000)
    assert state['done'],('Installer did not return',hex(u.reg_read(UC_ARM_REG_PC)))
    return u.reg_read(UC_ARM_REG_R0)
call(symbols['_Z9heap_initv'],[])
platform=0x07800080;u.mem_write(platform,struct.pack('<I',symbols['_ZTV20DSPicoLoaderPlatform']+8))
apply=next(v for k,v in symbols.items() if k.startswith('_ZNK11Arm9Patcher12ApplyPatches'))
call(apply,[0x07800100,platform,0,0,0,0x07800180])
wfi=struct.unpack('<I',u.mem_read(rom.arm9RamAddress+0x6bac,4))[0]
hooks=struct.unpack('<I',u.mem_read(symbols['_ZL10sWaitHooks'],4))[0]
report={'wfi_instruction':hex(wfi),'wfi_hooked':wfi!=0xee070f90,'total_wait_hooks':hooks,'allocations':state['allocations'],'requests':state['requests']}
assert report['wfi_hooked'] and hooks==5,report
u.mem_write(rom.arm7RamAddress,bytes(rom.arm7))
sectors=(0x4c9800 if P4 else 0x4c9600 if M32 else 0x424400 if M3 else 0x40c200)//512
words=[0x30505452 if P4 else 0x32565452 if M32 else 0x31435452 if M3 else 0x324d5452,0x40001 if P4 else 0x30002 if M32 else 0x30001 if M3 else 0x20001,sectors,1,0x800,0x10000,0x4a473241,0,sectors,0x1000]+[0]*62
words[7]=0x80000000 if full else 0
u.mem_write(symbols['gRtsSnapshotInfo'],struct.pack('<72I',*words))
if P4:u.mem_write(symbols['gRtsP4LoaderIdentity'],bytes.fromhex('078631bbdc625a13340b961ea902b9475b7efbc2869ddbbde5999638f47d5eb4')+b'\0'*48)
def prompt(uc,addr,size,data):
    state['warnings'].append(cstring(uc.reg_read(UC_ARM_REG_R0)))
    skip(uc,addr,size,data)
u.hook_add(UC_HOOK_CODE,prompt,begin=symbols['rtsProbeMessage'],end=symbols['rtsProbeMessage'])
arm7apply=next(v for k,v in symbols.items() if k.startswith('_ZNK11Arm7Patcher12ApplyPatches'))
call(arm7apply,[0x07800100,platform,0,0x07800120,0x07800124,0])
instruction,hook=struct.unpack('<II',u.mem_read(rom.arm7RamAddress+0x3c5c,8))
folder=root/('build/rts-worker-p4' if P4 else 'build/rts-worker-m32' if M32 else 'build/rts-worker-m3' if M3 else 'build/rts-worker')
meta=json.loads((folder/'RtsM2Image.json').read_text())
worker_literal=struct.unpack('<I',u.mem_read(symbols['_ZL16sM2EntryAtTarget'],4))[0]
worker=struct.unpack('<I',u.mem_read(worker_literal,4))[0]
assert instruction==0xe51ff004, state['warnings']
diagnostic_offset=symbols['rts7_diagnostic_address']-symbols['__start_patch_rts7']
diagnostic=struct.unpack('<I',u.mem_read(hook+diagnostic_offset,4))[0]
enabled_literal=struct.unpack('<I',u.mem_read(symbols['_ZL16sEnabledAtTarget'],4))[0]
enabled=struct.unpack('<I',u.mem_read(enabled_literal,4))[0]
assert instruction==0xe51ff004 and enabled==1
assert worker==0x023fa000
assert diagnostic==worker+meta['config_offset']+28
assert state['warnings'] and ('restore P4.2' if P4 else 'capture M3.2' if M32 else 'capture M3.1' if M3 else 'snapshot M2.6') in state['warnings'][-1],state['warnings']
for symbol,expected in [('rts7_read_busy_address','dspico_readsdsectors_busy'),('rts7_write_busy_address','dspico_writesdsectors_busy')]:
    literal=struct.unpack('<I',u.mem_read(hook+symbols[symbol]-symbols['__start_patch_rts7'],4))[0]
    assert 0x03800000<=literal<0x03810000,(symbol,hex(literal))
    assert bytes(u.mem_read(literal,4))==b'\0'*4
    report[symbol]=hex(literal)
clock=struct.unpack('<I',u.mem_read(hook+symbols['rts7_clock_address']-symbols['__start_patch_rts7'],4))[0]
assert clock==worker+meta['clock_offset'] and clock%32==0
assert clock+32<=worker+meta['config_offset']
assert struct.unpack('<I',u.mem_read(worker+meta['config_offset']+296+76,4))[0]==((4 if full else 6) if P4 else (1 if full else 3))
if not M3:assert ('FULL:' if full else 'FAST:') in state['warnings'][-1]
assert struct.unpack('<I',u.mem_read(diagnostic,4))[0]==0, 'Boot config leaked into runtime refusal word'
if M3:
    for label in ('mailbox','capture','service'):
        literal=struct.unpack('<I',u.mem_read(hook+symbols['rts7_'+label+'_address']-symbols['__start_patch_rts7'],4))[0]
        offset=meta[{'mailbox':'mailbox_offset','capture':'arm7_capture_offset','service':'arm7_service_offset'}[label]]
        assert literal==worker+offset
        report[label]=hex(literal)
if P4:
    ptr=struct.unpack('<13I',u.mem_read(worker+meta['p4_pointers_offset'],52))
    tail=struct.unpack('<I',u.mem_read(ptr[9],4))[0]
    assert 0x02000000<=tail and tail+meta['p4_tail_bytes']<=0x02000800
    assert bytes(u.mem_read(tail,meta['p4_tail_bytes']))==bytes(u.mem_read(ptr[8],meta['p4_tail_bytes']))
    assert bytes(u.mem_read(ptr[7],32))==bytes.fromhex('078631bbdc625a13340b961ea902b9475b7efbc2869ddbbde5999638f47d5eb4')
    assert bytes(u.mem_read(ptr[7]+32,32)).hex()==meta['p4_build_fingerprint']
    for literal,index in [('rts7_begin_address',1),('rts7_loop_address',0)]:
        assert struct.unpack('<I',u.mem_read(hook+symbols[literal]-symbols['__start_patch_rts7'],4))[0]==ptr[index]
    pcmPat=struct.pack('<II',0xe92d41f0,0xe1a08001);tmPat=struct.pack('<II',0xe2611801,0xe1a00200)
    for pattern in (pcmPat,tmPat):
        offset=bytes(rom.arm7).index(pattern);a=rom.arm7RamAddress+offset
        ins,stub=struct.unpack('<II',u.mem_read(a,8));assert ins==0xe51ff004 and 0x0380bc90<=stub<0x0380c490
    report['persistent_identity']='loaded code SHA + build fingerprint (full ROM host-verified)'
    report['secure_tail']=hex(tail)
report['clock']=hex(clock)
report['workspace_bytes']=meta['memory_bytes']
report.update({'arm7_hook':hex(hook),'worker':hex(worker),'diagnostic':hex(diagnostic),'enabled':enabled,'prompt':state['warnings'][-1]})
print(json.dumps({k:v for k,v in report.items() if k not in ('allocations','requests')},indent=2))
(folder/('installer-report-full.json' if full else 'installer-report.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
