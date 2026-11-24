"""Run both original and instrumented stackless CPU capture, without ROM input."""
from pathlib import Path
import os,struct,subprocess,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]);prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful'))/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC]
keys=[(1,0,0),(2,0,0),(2,0,1),(3,0,0),(5,0,2),(5,0,3)]+[(6,i,0) for i in range(8)]+[(9,1,0),(9,1,1),(9,0,0),(9,0,1),(13,0,1)]
def run(folder,trace):
 elf=r/'build'/folder/'worker.elf';syms={p[2]:int(p[0],16) for l in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=l.split())==3}
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_946)
 for a,n in [(0x02000000,0x400000),(0x027c0000,0x4000),(0x06840000,0x20000)]:u.mem_map(a,n)
 raw=elf.read_bytes();off=struct.unpack_from('<I',raw,28)[0];size,count=struct.unpack_from('<HH',raw,42)
 for i in range(count):
  typ,pos,a,pa,n,memsz,flags,align=struct.unpack_from('<8I',raw,off+i*size)
  if typ==1 and n:u.mem_write(a,raw[pos:pos+n])
 ctx=0x023f4000;done=0x02008000;events=[]
 for i,mode in enumerate((31,18,19,23,27,17)):
  u.reg_write(UC_ARM_REG_CPSR,0x600000c0|mode);u.reg_write(UC_ARM_REG_SP,0x027c1000+i*128);u.reg_write(UC_ARM_REG_LR,0x02001000+i*4)
  if mode!=31:u.reg_write(UC_ARM_REG_SPSR,0x8000001f+i*0x1000000)
  if mode==17:
   for j,reg in enumerate(regs[8:13]):u.reg_write(reg,0xf0000000+j)
 u.reg_write(UC_ARM_REG_CPSR,0x600000df);u.reg_write(UC_ARM_REG_SP,0x023f2000);u.reg_write(UC_ARM_REG_LR,done|1)
 for i,reg in enumerate(regs[:13]):u.reg_write(reg,0x12340000+i)
 for reg,value in zip(regs,[ctx,0x02010000,0x02000445,0x023e0021]):u.reg_write(reg,value)
 cp={key:0x10101*i for i,key in enumerate(keys,1)}
 def code(cpu,a,n,d):
  if a==done:cpu.emu_stop();return
  if trace and a==syms['rtsCpuTraceDigit']:
   events.append(cpu.reg_read(UC_ARM_REG_R3));return
  ins=struct.unpack('<I',cpu.mem_read(a,4))[0]
  if not cpu.reg_read(UC_ARM_REG_CPSR)&32 and ins&0x0f000f10==0x0e000f10:
   assert ins&(1<<20),'Capture wrote CP15'
   key=((ins>>16)&15,ins&15,(ins>>5)&7);rd=(ins>>12)&15;cpu.reg_write(regs[rd],cp[key]);cpu.reg_write(UC_ARM_REG_PC,a+4)
 def write(cpu,ac,a,n,value,d):
  assert ctx<=a and a+n<=ctx+512 or trace and 0x06840000<=a<0x06841000,('Touched game stack/RAM',hex(a))
 u.hook_add(UC_HOOK_CODE,code);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.emu_start(syms['rtsCaptureArm9Cpu'],0,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_SP)==0x023f2000
 assert [u.reg_read(reg) for reg in regs[4:12]]==[0x12340000+i for i in range(4,12)]
 if trace:
  assert events==list(range(1,29)),events
  font=bytes(u.mem_read(syms['gRtsDigits'],50))
  for digit,x in [(2,48),(8,54)]:
   for col in range(5):
    for y in range(7):
     pixel=struct.unpack('<H',u.mem_read(0x06840000+y*512+(x+col)*2,2))[0]
     assert pixel==(0xffff if font[digit*5+col]&(1<<y) else 0x8000),(digit,col,y,hex(pixel))
 return bytes(u.mem_read(ctx,512))
plain=run('rts-worker-p4',False);traced=run('rts-worker-p43',True)
assert plain==traced,'Tracing changed CPU state record'
print('PASS all 28 compiled trace stamps, readable 0028 glyphs, identical 512-byte CPU record, unchanged mode stacks/callee registers')
