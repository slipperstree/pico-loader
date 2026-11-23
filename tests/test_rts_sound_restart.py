"""Validate sound restart programming; optionally execute the real private SDK.
No speaker/audio-position emulation and no target bytes embedded in this test.
"""
import ctypes as C,json,os,struct,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]).resolve();f=r/'build/rts-sound-restart';f.mkdir(exist_ok=True)
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc');lib=f/('sound.dll' if os.name=='nt' else 'sound.so')
subprocess.run([cc,'-shared','-O2','-Wall','-Wextra','-I'+str(r/'common'),str(r/'runtime/rts/sound-restart.c'),'-o',str(lib)],check=True)
tc=Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful'));prefix=str(tc/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
if os.name=='nt':os.environ['PATH']=str(tc/'bin')+os.pathsep+str(Path(prefix).parent)+os.pathsep+os.environ['PATH']
subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-marm','-Os','-ffreestanding','-fno-builtin','-Wall','-Wextra','-I'+str(r/'common'),'-c',str(r/'runtime/rts/sound-restart.c'),'-o',str(f/'sound.arm.o')],check=True)
class Channel(C.Structure):_fields_=[(x,C.c_uint32) for x in ('control','source','timer','loop','length')]
class Shadow(C.Structure):_fields_=[(x,C.c_uint32) for x in ('magic','version','sequence','unsupported')]+[('channels',Channel*16),('coverage',C.c_uint32*16),('reserved',C.c_uint32*28)]
class Plan(C.Structure):_fields_=[(x,C.c_uint32) for x in ('magic','version','master','bias','activeMask','sequence')]+[('channels',Channel*16),('reserved',C.c_uint32*42)]
assert C.sizeof(Shadow)==C.sizeof(Plan)==512
native=C.CDLL(str(lib));init=native.RtsInitSoundShadow;observe=native.RtsObserveSoundWrite;build=native.RtsBuildSoundRestart
init.argtypes=[C.POINTER(Shadow)];observe.argtypes=[C.POINTER(Shadow),C.c_uint32,C.c_uint32,C.c_uint32]
build.argtypes=[C.POINTER(Shadow),C.POINTER(C.c_uint32),C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Plan)]
Writer=C.CFUNCTYPE(None,C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32)
for name in ('RtsPrepareSoundRestart','RtsReleaseSoundRestart'):getattr(native,name).argtypes=[C.POINTER(Plan),Writer,C.c_void_p]
def make_shadow():
 s=Shadow();init(C.byref(s))
 for ch in range(16):
  a=0x04000400+ch*16
  for off,n,v in [(0,4,(ch%3<<29)|(1<<27)|(64<<16)|80),(4,4,0x02040000+ch*0x400),(8,2,0xfe00),(10,2,4),(12,4,16)]:assert observe(C.byref(s),a+off,n,v)==1
 return s
def plan(s,controls=None,expected=0,capture=0):
 if controls is None:controls=[c.control|0x80000000 for c in s.channels]
 out=Plan();C.memset(C.byref(out),0xa5,512)
 assert build(C.byref(s),(C.c_uint32*16)(*controls),0x807f,512,capture,C.byref(out))==expected
 if expected:assert C.string_at(C.byref(out),512)==b'\xa5'*512
 return out
def programming(p):
 events=[]
 @Writer
 def write(user,a,n,v):events.append((a,n,v))
 native.RtsPrepareSoundRestart(C.byref(p),write,None)
 assert events[0]==(0x04000500,2,0)
 assert all(not (a<0x04000500 and (a-0x04000400)%16==0 and v&0x80000000) for a,n,v in events),'Channel started during prepare'
 assert events[1:17]==[(0x04000400+i*16,4,0) for i in range(16)]
 for ch in range(16):
  if not p.activeMask&(1<<ch):continue
  c=p.channels[ch];a=0x04000400+ch*16
  assert (a+8,2,c.timer) in events
  if (c.control>>29)&3!=3:
   for event in ((a+4,4,c.source),(a+10,2,c.loop),(a+12,4,c.length)):assert event in events
 before=len(events);native.RtsReleaseSoundRestart(C.byref(p),write,None)
 expected=[(0x04000400+ch*16,4,p.channels[ch].control) for ch in range(16) if p.activeMask&(1<<ch)]+[(0x04000500,2,p.master)]
 assert events[before:]==expected
 assert all(0x04000400<=a<=0x04000504 for a,n,v in events)
s=make_shadow();programming(plan(s))
damaged=make_shadow();damaged.coverage[3]&=~0xf0;plan(damaged,expected=2)
damaged=make_shadow();damaged.channels[3].source=0x04000400;plan(damaged,expected=3)
damaged=make_shadow();damaged.channels[3].source=0x023ffffc;plan(damaged,expected=3)
damaged=make_shadow();assert observe(C.byref(damaged),0x04000401,4,0)==-1;plan(damaged,expected=1)
plan(s,expected=1,capture=0x80)
psg=Shadow();init(C.byref(psg));assert observe(C.byref(psg),0x04000488,2,0xfe00)==1
controls=[0]*16;controls[8]=0xe000007f;programming(plan(psg,controls))
controls[7]=controls[8];psg.coverage[7]=0x300;plan(psg,controls,expected=3)
split=Shadow();init(C.byref(split));observe(C.byref(split),0x04000404,2,0x1234);observe(C.byref(split),0x04000406,2,0x0200)
assert split.channels[0].source==0x02001234 and split.coverage[0]&0xf0==0xf0
print('PASS sound byte/halfword/word shadow, active-field coverage/source guards, PCM/ADPCM/PSG prepare and delayed restart')
sdk=False
if len(sys.argv)>2:
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
 from unicorn.arm_const import *
 blob=Path(sys.argv[2]).read_bytes();assert len(blob)==0x4c9600
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a,n in [(0x02000000,0x400000),(0x037f8000,0x18000),(0x04000000,0x1000)]:u.mem_map(a,n)
 u.mem_write(0x03800000,blob[512+0x40c200:512+0x41c200]);u.mem_write(0x037f8000,blob[512+0x41c200:512+0x424200])
 # These are observed setter globals; disable optional pan override/surround
 # processing in the model to isolate hardware parameter writes.
 u.mem_write(0x0380819c,struct.pack('<I',0xffffffff));u.mem_write(0x03808548,b'\0'*4)
 entry=0x037ff298;assert bytes(u.mem_read(entry,4))==struct.pack('<I',0xe92d41f0)
 captured=Shadow();init(C.byref(captured));done=0x020f0000;u.mem_write(done,b'\x1e\xff\x2f\xe1')
 def write(uc,ac,a,n,v,d):assert observe(C.byref(captured),a,n,v)==1
 u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x04000400,end=0x040004ff)
 for ch in range(16):
  sp=0x0380f000;u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done)
  for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(ch,0x02040000+ch*0x400,ch%3,1)):u.reg_write(reg,v)
  u.mem_write(sp,struct.pack('<6I',4,16,80,0,512,64));u.emu_start(entry,done,count=5000)
  assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_SP)==sp
  got=captured.channels[ch];want=s.channels[ch]
  assert C.string_at(C.byref(got),20)==C.string_at(C.byref(want),20),(ch,[getattr(got,n) for n,t in Channel._fields_])
  assert captured.coverage[ch]==0xffff
 programming(plan(captured));sdk=True
 print('PASS actual private ARM7 SDK PCM setup for all 16 channels yields exact recorded parameters and restart programming')
(f/'RESULTS.json').write_text(json.dumps({'shadow_and_coverage_guards':'PASS','muted_prepare_and_delayed_release':'PASS','private_sdk_16_channels':'PASS' if sdk else 'not supplied','hardware_playback_tested':False,'exact_audio_position_restored':False,'runtime_hooks_installed':False},indent=2))
