"""Execute the actual ARM7TDMI capture helpers; model RAM/mapping, not hardware."""
import struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
 UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
 UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
class Arm7CaptureModel:
 def __init__(self,image,meta,base=0x023fa000,mode=0x12,wram=3):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.meta=meta;self.base=base
  for a,n in [(0x02000000,0x400000),(0x03000000,0x8000),(0x03800000,0x10000),(0x04000000,0x1000)]:u.mem_map(a,n)
  relocated=bytearray(image)
  for offset in meta['relocations']:
   value=struct.unpack_from('<I',relocated,offset)[0]
   struct.pack_into('<I',relocated,offset,value+base-meta['link_base'])
  u.mem_write(base,bytes(relocated))
  self.mailbox=base+meta['mailbox_offset'];self.ctx=self.mailbox+544
  self.private=bytes((i*37+i//256)%256 for i in range(0x10000))
  self.shared=bytes((i*13+123+i//512)%256 for i in range(0x8000))
  u.mem_write(0x03800000,self.private);u.mem_write(0x03000000,self.shared)
  u.mem_write(0x04000241,bytes([wram]));self.parkSp=0x0380f000
  self.banks=[]
  for i,m in enumerate((31,18,19,23,27,17)):
   u.reg_write(UC_ARM_REG_CPSR,0xc0|m)
   sp=self.parkSp if m==mode else 0x03808000+i*256
   lr=0x03801000+i*4;spsr=0 if m==31 else 0xa000001f+i*0x10000000
   u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,lr)
   if m!=31:u.reg_write(UC_ARM_REG_SPSR,spsr)
   self.banks.append((sp,lr,spsr&0xffffffff))
  self.fiq=[0xf0000000+i for i in range(5)]
  for reg,v in zip(REGS[8:],self.fiq):u.reg_write(reg,v)
  u.reg_write(UC_ARM_REG_CPSR,0x600000c0|mode)
  u.reg_write(UC_ARM_REG_SP,self.parkSp)
  self.saved=[0x12340000+i for i in range(12)];self.saved[-1]=self.banks[0 if mode==31 else 1][1]
  u.mem_write(self.parkSp,struct.pack('<12I',*self.saved))
  for i,reg in enumerate(REGS[4:12]):u.reg_write(reg,0xcafe0000+i)
  self.done=0x020f0000;u.mem_write(self.done,b'\x1e\xff\x2f\xe1')
  self.beforePrivate=bytes(u.mem_read(0x03800000,0x10000));self.beforeShared=self.shared
  self.writes=[]
  u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,ac,a,n,v,d:self.writes.append((a,n)))
  self.call('arm7_capture',[self.mailbox,self.parkSp,0xa0000000|mode,1])
  self.context=bytes(u.mem_read(self.ctx,512))
 def call(self,name,args):
  u=self.u;before=[u.reg_read(x) for x in REGS[4:12]];sp=u.reg_read(UC_ARM_REG_SP)
  for reg,v in zip(REGS,args):u.reg_write(reg,v)
  u.reg_write(UC_ARM_REG_LR,self.done)
  u.emu_start(self.base+self.meta[name+'_offset'],self.done,count=10000)
  assert u.reg_read(UC_ARM_REG_PC)==self.done,'ARM7 helper failed to return'
  assert before==[u.reg_read(x) for x in REGS[4:12]] and sp==u.reg_read(UC_ARM_REG_SP)
  assert bytes(u.mem_read(0x03800000,0x10000))==self.beforePrivate,'Private WRAM modified'
  assert bytes(u.mem_read(0x03000000,0x8000))==self.beforeShared,'Shared WRAM modified'
  assert all(self.mailbox<=a and a+n<=self.mailbox+1056 for a,n in self.writes),'Unexpected guest write'
 def block(self,index,request):
  self.u.mem_write(self.mailbox,struct.pack('<5I',1,request,request-1,0,index))
  self.call('arm7_service',[self.mailbox])
  result=bytes(self.u.mem_read(self.mailbox,544))
  assert struct.unpack_from('<I',result,8)[0]==request
  return struct.unpack_from('<I',result,12)[0],result[32:]
