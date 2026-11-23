"""Execute original SDK versus instrumented SDK, using a private M3.2 input.
No SDK bytes are distributed and no live ROM/TF file is modified.
"""
import ctypes as C,importlib.util,json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();snapshot=Path(sys.argv[2]);blob=snapshot.read_bytes();assert len(blob)==0x4c9600
spec=importlib.util.spec_from_file_location('sound',r/'tests/test_rts_sound_restart.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
f=r/'build/rts-sound-hooks';f.mkdir(exist_ok=True);prefix=s.prefix
ld=f/'hooks.ld';ld.write_text('SECTIONS { . = 0x023fa000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } .bss (NOLOAD) : { *(.bss*) *(COMMON) } . = 0x0380c400; .pcm : { *(patch_rtsSoundPcm) } . = 0x0380c500; .timer : { *(patch_rtsSoundTimer) } . = 0x0380c600; .exit : { *(patch_rtsSoundExit) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } }')
elf=f/'hooks.elf';subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-marm','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-DPICO_RTS_AUDIO_SHADOW','-nostdlib','-Wl,--build-id=none,-e,rtsSoundObservePcm','-I'+str(r/'common'),'-T',str(ld),str(r/'runtime/rts/sound-observer.c'),str(r/'runtime/rts/sound-restart.c'),str(r/'arm9/source/patches/rts/RtsSoundHooks7.s'),'-o',str(elf)],check=True)
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=line.split())==3}
raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
pcm,timer,pcmExit,timerExit=0x037ff298,0x037ff068,0x037ff350,0x037ff07c
def model(patched):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a,n in [(0x02000000,0x400000),(0x037f8000,0x18000),(0x04000000,0x1000)]:u.mem_map(a,n)
 u.mem_write(0x03800000,blob[512+0x40c200:512+0x41c200]);u.mem_write(0x037f8000,blob[512+0x41c200:512+0x424200])
 u.mem_write(0x0380819c,struct.pack('<I',0xffffffff));u.mem_write(0x03808548,b'\0'*4)
 assert bytes(u.mem_read(pcm,8))==struct.pack('<II',0xe92d41f0,0xe1a08001)
 assert bytes(u.mem_read(timer,8))==struct.pack('<II',0xe2611801,0xe1a00200)
 if patched:
  for i in range(phnum):
   kind,off,a,pa,n,memsize,flags,align=struct.unpack_from('<8I',raw,phoff+i*phsize)
   if kind==1 and n:u.mem_write(a,raw[off:off+n])
  shadow=s.Shadow();s.init(C.byref(shadow));u.mem_write(syms['gRtsSoundShadow'],C.string_at(C.byref(shadow),512))
  for name,helper,resume in [('Pcm','rtsSoundObservePcm',pcm+8),('Timer','rtsSoundObserveTimer',timer+8)]:
   for literal,value in [('Busy',syms['gRtsSoundBusy']),('Observe',syms[helper]),('Resume',resume)]:u.mem_write(syms['rtsSound'+name+literal],struct.pack('<I',value))
  u.mem_write(syms['rtsSoundExitBusy'],struct.pack('<I',syms['gRtsSoundBusy']))
  for entry,name in [(pcm,'Pcm'),(timer,'Timer')]:u.mem_write(entry,struct.pack('<II',0xe51ff004,syms['rtsSound'+name+'Hook']))
  for exit in (pcmExit,timerExit):
   assert bytes(u.mem_read(exit,4))==struct.pack('<I',0xe12fff1e)
   delta=(syms['rtsSoundExitHook']-exit-8)>>2;u.mem_write(exit,struct.pack('<I',0xea000000|(delta&0xffffff)))
 done=0x020f0000;u.mem_write(done,b'\x1e\xff\x2f\xe1');events=[]
 def write(uc,ac,a,n,v,d):
  if patched:assert struct.unpack('<I',uc.mem_read(syms['gRtsSoundBusy'],4))[0]>0,'SDK wrote MMIO after busy was prematurely cleared'
  events.append((a,n,v))
 u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x04000400,end=0x040004ff)
 def call(entry,ch,period=512):
  sp=0x0380f000;u.reg_write(UC_ARM_REG_CPSR,0xa000001f);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done)
  for i,reg in enumerate(regs):u.reg_write(reg,0x12340000+i)
  args=(ch,0x02040000+ch*0x400,ch%3,1) if entry==pcm else (ch,period,0,0)
  for reg,v in zip(regs,args):u.reg_write(reg,v)
  if entry==pcm:u.mem_write(sp,struct.pack('<6I',4,16,80,0,period,64))
  before=len(events);u.emu_start(entry,done,count=20000)
  assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_SP)==sp
  if patched:assert struct.unpack('<I',u.mem_read(syms['gRtsSoundBusy'],4))[0]==0
  return ([u.reg_read(reg) for reg in regs]+[u.reg_read(UC_ARM_REG_LR),u.reg_read(UC_ARM_REG_CPSR)],events[before:])
 return u,call
plain,original=model(False);hooked,observed=model(True)
for ch in range(16):
 assert original(pcm,ch)==observed(pcm,ch),'PCM instrumentation changed ABI or hardware writes'
 assert original(timer,ch,256+ch)==observed(timer,ch,256+ch),'Timer instrumentation changed ABI or hardware writes'
shadow=s.Shadow.from_buffer_copy(bytes(hooked.mem_read(syms['gRtsSoundShadow'],512)))
controls=[]
for ch in range(16):
 c=shadow.channels[ch]
 assert (c.source,c.timer,c.loop,c.length)==(0x02040000+ch*0x400,(0x10000-256-ch)&65535,4,16)
 assert shadow.coverage[ch]&0xfff0==0xfff0
 controls.append(struct.unpack('<I',hooked.mem_read(0x04000400+ch*16,4))[0]|0x80000000)
s.programming(s.plan(shadow,controls))
print('PASS actual PCM and timer SDK with compiled ARM7 hooks: all 16 channels identical writes/registers/flags/stack; shadow parameters valid; busy spans whole calls')
(f/'RESULTS.json').write_text(json.dumps({'real_sdk_with_hooks_16_channels':'PASS','unchanged_mmio_and_abi':'PASS','busy_through_complete_sdk_call':'PASS','recorded_restart_parameters':'PASS','native_restart_plan_from_hooked_calls':'PASS','live_installed':False},indent=2))
