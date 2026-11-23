"""Execute unlinked ARM7 restore primitives on cold/mutated memory and banks.
Optional private capture is never copied into source/artifacts. No hardware load.
"""
import ctypes as C,json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from arm7_capture_model import Arm7CaptureModel,REGS
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
f=r/'build/rts-arm7-restore';f.mkdir(exist_ok=True)
tc=Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful'));prefix=str(tc/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
if os.name=='nt':os.environ['PATH']=str(tc/'bin')+os.pathsep+str(Path(prefix).parent)+os.pathsep+os.environ['PATH']
subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-marm','-nostdlib','-Wl,--build-id=none,-Ttext=0x02200000,-e,rtsArm7RestoreSector',str(r/'runtime/rts/arm7-restore.s'),'-o',str(f/'restore.elf')],check=True)
subprocess.run([prefix+'objcopy','-O','binary',str(f/'restore.elf'),str(f/'restore.bin')],check=True)
subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-marm','-Os','-Wall','-Wextra','-ffreestanding','-fno-builtin','-I'+str(r/'common'),'-c',str(r/'runtime/rts/arm7-restore.c'),'-o',str(f/'validator.arm.o')],check=True)
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
lib=f/('validator.dll' if os.name=='nt' else 'validator.so')
subprocess.run([cc,'-shared','-O2','-Wall','-Wextra','-I'+str(r/'common'),str(r/'runtime/rts/arm7-restore.c'),'-o',str(lib)],check=True)
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(f/'restore.elf')],text=True).splitlines() if len(p:=line.split())==3}
Reader=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32)
native=C.CDLL(str(lib));validate=native.RtsValidateArm7Continuation
validate.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_int,Reader,C.c_void_p];validate.restype=C.c_int
def check(context,regions,verified=True,fail=False):
 @Reader
 def reader(user,a,dst,n):
  if fail:return 0
  if 0x03000000<=a<0x03800000:a=0x03000000+(a&0x7fff)
  elif 0x03800000<=a<0x04000000:a=0x03800000+(a&0xffff)
  for base,data in regions:
   if base<=a and a+n<=base+len(data):C.memmove(dst,data[a-base:a-base+n],n);return 1
  return 0
 return validate(C.create_string_buffer(context),0x023fa000,0x3000,int(verified),reader,None)

def run(label,context,private,shared,main=None):
 h=struct.unpack('<128I',context);regions=[(0x03800000,private),(0x03000000,shared)]
 if main is not None:regions.append((0x02000000,main))
 assert check(context,regions)==0,(label,'context validation')
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a,n in [(0x02000000,0x400000),(0x03000000,0x800000),(0x03800000,0x10000),(0x04000000,0x1000)]:u.mem_map(a,n)
 u.mem_write(0x02000000,b'\xcc'*0x400000);u.mem_write(0x03800000,b'\xdd'*0x10000);u.mem_write(0x03000000,b'\xee'*0x8000)
 u.mem_write(0x02200000,(f/'restore.bin').read_bytes());ctx=0x023fa100;stage=0x023fa400;done=0x023fb000
 u.mem_write(ctx,context);u.mem_write(done,b'\x1e\xff\x2f\xe1');u.mem_write(0x04000241,b'\x03')
 state={'range':None,'phase':'write','writes':0}
 def write(uc,ac,a,n,v,d):
  if state['phase']=='write':assert state['range'] and state['range'][0]<=a and a+n<=state['range'][1],('Unexpected write',hex(a))
  else:assert a==0x04000208 and n==4 and v==h[4],('Return wrote memory',hex(a))
  if 0x03000000<=a<0x03008000:uc.mem_write(0x037f8000+(a&0x7fff),int(v).to_bytes(n,'little'))
  state['writes']+=1
 u.hook_add(UC_HOOK_MEM_WRITE,write)
 def sector(block,src=stage,cpsr=0xdf,ime=0,wram=3,lr=done):
  u.mem_write(0x04000208,struct.pack('<I',ime));u.mem_write(0x04000241,bytes([wram]))
  u.reg_write(UC_ARM_REG_CPSR,cpsr);u.reg_write(UC_ARM_REG_SP,0x023fc000);u.reg_write(UC_ARM_REG_LR,lr)
  u.reg_write(UC_ARM_REG_R0,block);u.reg_write(UC_ARM_REG_R1,src)
  u.emu_start(syms['rtsArm7RestoreSector'],lr&~1,count=3000)
  assert u.reg_read(UC_ARM_REG_PC)==lr&~1 and u.reg_read(UC_ARM_REG_SP)==0x023fc000
  return u.reg_read(UC_ARM_REG_R0)
 for i in range(192):
  data=private[i*512:(i+1)*512] if i<128 else shared[(i-128)*512:(i-127)*512]
  u.mem_write(stage,data);dest=0x03800000+i*512 if i<128 else 0x03000000+(i-128)*512
  state['range']=(dest,dest+512);before=state['writes']
  assert sector(i)==1 and state['writes']==before+128
 assert bytes(u.mem_read(0x03800000,0x10000))==private and bytes(u.mem_read(0x03000000,0x8000))==shared
 before=state['writes'];state['range']=None
 for kw in ({'block':192},{'block':0,'src':stage+1},{'block':0,'src':0x03800000},{'block':0,'ime':1},{'block':0,'cpsr':0x1f},{'block':128,'wram':2},{'block':0,'lr':0x03800000}):
  assert sector(**kw)==0 and state['writes']==before
 # Clobber every bank, all general registers and the active stack, so a no-op
 # return cannot pass. Restore primitive must reconstruct the captured values.
 for mode in (31,18,19,23,27,17):
  u.reg_write(UC_ARM_REG_CPSR,0xc0|mode);u.reg_write(UC_ARM_REG_SP,0x03807000+mode*16);u.reg_write(UC_ARM_REG_LR,0xdead0000+mode)
  if mode!=31:u.reg_write(UC_ARM_REG_SPSR,0x10)
  if mode==17:
   for reg in REGS[8:]:u.reg_write(reg,0xdeadbeef)
 u.reg_write(UC_ARM_REG_CPSR,0xdf)
 for reg in REGS:u.reg_write(reg,0xbad0bad0)
 u.reg_write(UC_ARM_REG_R0,ctx);u.mem_write(0x04000208,b'\0'*4);state['phase']='return'
 pc=h[19]&~1;u.emu_start(syms['rtsEnterArm7Continuation'],pc,count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==pc and u.reg_read(UC_ARM_REG_CPSR)==(h[3]|(0x20 if h[19]&1 else 0))
 assert [u.reg_read(reg) for reg in REGS[2:]]==list(h[8:19])
 assert u.reg_read(UC_ARM_REG_SP)==h[2]+48 and u.reg_read(UC_ARM_REG_LR)==h[19]
 for i,mode in enumerate((31,18,19,23,27,17)):
  u.reg_write(UC_ARM_REG_CPSR,0xc0|mode)
  assert u.reg_read(UC_ARM_REG_SP)==h[20+i*3]+(48 if mode==18 else 0)
  assert u.reg_read(UC_ARM_REG_LR)==h[21+i*3]
  if mode!=31:assert u.reg_read(UC_ARM_REG_SPSR)==h[22+i*3]
  if mode==17:assert [u.reg_read(reg) for reg in REGS[8:]]==list(h[38:43])
 assert bytes(u.mem_read(0x03800000,0x10000))==private and bytes(u.mem_read(0x03000000,0x8000))==shared
 print('PASS',label,'restored all 192 WRAM sectors from cold data and six register banks; reached saved IRQ caller; guard failures made no writes')
 # Validation remains read-only and does not accept unsupported/partial state.
 assert check(context,regions,verified=False)==1 and check(context,regions,fail=True)==6
 for word,value in [(0,0),(3,0x1f),(2,0x023fa100),(19,0x04000000),(23,h[23]+4),(8,h[8]^1)]:
  damaged=bytearray(context);struct.pack_into('<I',damaged,word*4,value)
  assert check(bytes(damaged),regions)!=0,(word,'bad context accepted')

folder=r/'build/rts-worker-m32';meta=json.loads((folder/'RtsM2Image.json').read_text());a=Arm7CaptureModel((folder/'worker.bin').read_bytes(),meta,mode=18)
context=bytearray(a.context);struct.pack_into('<I',context,12,struct.unpack_from('<I',context,12)[0]|0x80)
run('synthetic ARM7 IRQ',bytes(context),a.beforePrivate,a.shared)
if len(sys.argv)>2:
 blob=Path(sys.argv[2]).read_bytes();assert len(blob)==0x4c9600
 run('private M3.2 hardware capture',blob[512+0x40c000:512+0x40c200],blob[512+0x40c200:512+0x41c200],blob[512+0x41c200:512+0x424200],blob[512:512+0x400000])
(f/'RESULTS.json').write_text(json.dumps({'cold_wram_restore_192_sectors':'PASS','banked_cpu_restore_irq':'PASS','bounds_irq_ime_wram_guards':'PASS','context_validator_negatives':'PASS','private_capture':'PASS' if len(sys.argv)>2 else 'not supplied','live_restore_enabled':False,'full_game_restore_tested':False},indent=2))
