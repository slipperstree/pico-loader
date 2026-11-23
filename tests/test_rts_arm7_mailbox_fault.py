"""Execute actual ARM9 mailbox timeout/refusal paths, without a sector device."""
import json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
f=r/'build/rts-worker-m3';meta=json.loads((f/'RtsM2Image.json').read_text());base=meta['link_base']
prefix=os.environ.get('ARM_NONE_EABI_PREFIX','C:/msys64/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(f/'worker.elf')],text=True).splitlines() if len(p:=line.split())==3}
for status,expected in [(None,8008),(1,8021),(2,8022)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,0x10000);u.mem_map(0x04000000,0x2000)
 u.mem_write(base,(f/'worker.bin').read_bytes());m=base+meta['mailbox_offset'];clock=base+meta['clock_offset'];state={'frames':0,'fault':False,'card':False}
 def read(uc,ac,a,n,v,d):
  if a==clock:
   state['frames']+=1;uc.mem_write(clock,struct.pack('<I',state['frames']))
  if a==m+8 and status is not None:
   request=struct.unpack('<I',uc.mem_read(m+4,4))[0]
   uc.mem_write(m+12,struct.pack('<I',status));uc.mem_write(m+8,struct.pack('<I',request))
 def write(uc,ac,a,n,v,d):
  if 0x040001a0<=a<=0x040001af:state['card']=True
  if a==0x04000180 and (v>>8)&15==14:state['fault']=True;uc.emu_stop()
 u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,base+0xf000);u.reg_write(UC_ARM_REG_LR,base+0xff00);u.reg_write(UC_ARM_REG_R0,0)
 u.emu_start(syms['arm7Block'],0,count=100000)
 error=struct.unpack('<I',u.mem_read(base+meta['config_offset']+296+72,4))[0]
 assert error==expected and state['fault'] and not state['card'],(error,state)
 print('PASS ARM7 mailbox fails closed without SD command, readable code',error)
