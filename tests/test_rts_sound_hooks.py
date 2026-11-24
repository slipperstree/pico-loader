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
ld=f/'hooks.ld';ld.write_text('SECTIONS { . = 0x023fa000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } .bss (NOLOAD) : { *(.bss*) *(COMMON) } . = 0x0380c400; .pcm : { *(patch_rtsSoundPcm) } . = 0x0380c500; .timer : { *(patch_rtsSoundTimer) } . = 0x0380c600; .exit : { *(patch_rtsSoundExit) } . = 0x0380c700; .reload : { *(patch_rtsSoundReload) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } }')
elf=f/'hooks.elf';subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-marm','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-DPICO_RTS_AUDIO_SHADOW','-nostdlib','-Wl,--build-id=none,-e,rtsSoundObservePcm','-I'+str(r/'common'),'-T',str(ld),str(r/'runtime/rts/sound-observer.c'),str(r/'runtime/rts/sound-restart.c'),str(r/'arm9/source/patches/rts/RtsSoundHooks7.s'),'-o',str(elf)],check=True)
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=line.split())==3}
raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
pcm,timer,pcmExit,timerExit=0x037ff298,0x037ff068,0x037ff350,0x037ff07c
psg,noise,psgExit,noiseExit=0x037ff1e0,0x037ff130,0x037ff280,0x037ff1c8
def model(patched):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for a,n in [(0x02000000,0x400000),(0x037f8000,0x18000),(0x04000000,0x1000)]:u.mem_map(a,n)
 u.mem_write(0x03800000,blob[512+0x40c200:512+0x41c200]);u.mem_write(0x037f8000,blob[512+0x41c200:512+0x424200])
 u.mem_write(0x0380819c,struct.pack('<I',0xffffffff));u.mem_write(0x03808548,b'\0'*4)
 assert bytes(u.mem_read(pcm,8))==struct.pack('<II',0xe92d41f0,0xe1a08001)
 assert bytes(u.mem_read(timer,8))==struct.pack('<II',0xe2611801,0xe1a00200)
 for entry in (psg,noise):assert bytes(u.mem_read(entry,8))==struct.pack('<II',0xe92d40f0,0xe24dd004)
 if patched:
  for i in range(phnum):
   kind,off,a,pa,n,memsize,flags,align=struct.unpack_from('<8I',raw,phoff+i*phsize)
   if kind==1 and n:u.mem_write(a,raw[off:off+n])
  shadow=s.Shadow();s.init(C.byref(shadow));u.mem_write(syms['gRtsSoundShadow'],C.string_at(C.byref(shadow),512))
  for name,helper,resume in [('Pcm','rtsSoundObservePcm',pcm+8),('Timer','rtsSoundObserveTimer',timer+8)]:
   for literal,value in [('Busy',syms['gRtsSoundBusy']),('Observe',syms[helper]),('Resume',resume)]:u.mem_write(syms['rtsSound'+name+literal],struct.pack('<I',value))
  u.mem_write(syms['rtsSoundExitBusy'],struct.pack('<I',syms['gRtsSoundBusy']))
  for entry,name in ((pcm,'Pcm'),(timer,'Timer')):u.mem_write(entry,struct.pack('<II',0xe51ff004,syms['rtsSound'+name+'Hook']))
  for exit in (pcmExit,timerExit):
   assert bytes(u.mem_read(exit,4))==struct.pack('<I',0xe12fff1e)
   delta=(syms['rtsSoundExitHook']-exit-8)>>2;u.mem_write(exit,struct.pack('<I',0xea000000|(delta&0xffffff)))
  u.mem_write(syms['rtsSoundReloadObserve'],struct.pack('<I',syms['rtsSoundObserveReload']))
  if patched!='legacy':
   for at in (psg+0x94,noise+0x8c):
    assert bytes(u.mem_read(at,4))==struct.pack('<I',0xe1c010b8)
    delta=(syms['rtsSoundReloadHook']-at-8)>>2;u.mem_write(at,struct.pack('<I',0xeb000000|(delta&0xffffff)))
 done=0x020f0000;u.mem_write(done,b'\x1e\xff\x2f\xe1');events=[];guard=[False];atomic=[False]
 def write(uc,ac,a,n,v,d):
  if guard[0]:assert struct.unpack('<I',uc.mem_read(syms['gRtsSoundBusy'],4))[0]>0,'SDK wrote MMIO after busy was prematurely cleared'
  if atomic[0] and n==2 and (a-0x04000400)%16==8:
   assert uc.reg_read(UC_ARM_REG_CPSR)&0xc0==0xc0,'PSG/noise shadow/store not interrupt-atomic'
   ch=(a-0x04000408)//16
   assert struct.unpack('<I',uc.mem_read(syms['gRtsSoundShadow']+16+ch*20+8,4))[0]==v&65535
   assert struct.unpack('<I',uc.mem_read(syms['gRtsSoundShadow']+336+ch*4,4))[0]&0x300==0x300
   assert not struct.unpack('<I',uc.mem_read(0x04000400+ch*16,4))[0]&0x80000000,'Channel was active before its TMR setup'
  events.append((a,n,v))
 u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x04000400,end=0x040004ff)
 def call(entry,ch,period=512):
  sp=0x0380f000;u.reg_write(UC_ARM_REG_CPSR,0xa000001f);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done)
  for i,reg in enumerate(regs):u.reg_write(reg,0x12340000+i)
  guard[0]=bool(patched) and entry in (pcm,timer)
  atomic[0]=bool(patched) and patched!='legacy' and entry in (psg,noise)
  if entry==pcm:args=(ch,0x02040000+ch*0x400,ch%3,1)
  elif entry==psg:args=(ch,ch%8,80,1)
  elif entry==noise:args=(ch,80,1,period)
  else:args=(ch,period,0,0)
  for reg,v in zip(regs,args):u.reg_write(reg,v)
  if entry==pcm:u.mem_write(sp,struct.pack('<6I',4,16,80,0,period,64))
  elif entry==psg:u.mem_write(sp,struct.pack('<2I',period,64))
  elif entry==noise:u.mem_write(sp,struct.pack('<I',64))
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

# Reproduce the user's cold-launch symptom with only the legacy PCM/Timer
# observation points: PSG11 active lacks TMR coverage; stopped PSG11 passes.
legacy,legacyCall=model('legacy');legacyCall(psg,11,777)
shadow=s.Shadow.from_buffer_copy(bytes(legacy.mem_read(syms['gRtsSoundShadow'],512)))
controls=[0]*16;controls[11]=struct.unpack('<I',legacy.mem_read(0x040004b0,4))[0]|0x80000000
s.inspect(shadow,controls,2,4411)
controls[11]&=~0x80000000;s.inspect(shadow,controls,0,0)
assert shadow.coverage[11]==0
cold,coldCall=model(True);coldCall(psg,11,777)
shadow=s.Shadow.from_buffer_copy(bytes(cold.mem_read(syms['gRtsSoundShadow'],512)))
controls[11]=struct.unpack('<I',cold.mem_read(0x040004b0,4))[0]|0x80000000
plan=s.inspect(shadow,controls,0,0)
assert shadow.coverage[11]==0x300 and plan.channels[11].timer==(0x10000-777)&65535
print('PASS cold PSG11: legacy observer reproduces 4411 until stopped; added PSG observation makes the first active preflight valid')
for entry,channels in ((psg,range(8,14)),(noise,range(14,16))):
 plain,original=model(False);hooked,observed=model(True)
 controls=[0]*16
 for ch in channels:
  period=777+ch
  assert original(entry,ch,period)==observed(entry,ch,period),'PSG/noise observation changed SDK ABI or hardware writes'
  controls[ch]=struct.unpack('<I',hooked.mem_read(0x04000400+ch*16,4))[0]|0x80000000
 shadow=s.Shadow.from_buffer_copy(bytes(hooked.mem_read(syms['gRtsSoundShadow'],512)))
 for ch in channels:
  assert shadow.coverage[ch]==0x300 and shadow.channels[ch].timer==(0x10000-777-ch)&65535
  assert shadow.channels[ch].source==shadow.channels[ch].loop==shadow.channels[ch].length==0
 s.programming(s.plan(shadow,controls))
print('PASS actual PSG 8..13 and noise 14..15 SDK: identical writes/registers/flags/stack, observed timers, IRQ-atomic shadow/TMR store, restart plan valid')
result=json.loads((f/'RESULTS.json').read_text());result.update({'psg_noise_sdk_abi':'PASS','psg_noise_atomic_timer':'PASS','cold_psg11_legacy_4411_reproduced':'PASS','cold_psg11_first_preflight':'PASS'})
(f/'RESULTS.json').write_text(json.dumps(result,indent=2))
