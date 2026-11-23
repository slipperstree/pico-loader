"""Execute P4's real private VBlank hook and main-RAM ARM7 RPC loop."""
from pathlib import Path
import sys,subprocess,struct,os
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import *
root=Path(sys.argv[1]).resolve();model=Path(__file__).with_name('test_rts_p4_worker.py')
exec(compile(model.read_text().split('disk={physical[0]:bytes(blank)}')[0],str(model),'exec'),globals())
elf=root/'build/picoLoader9_DSPICO_restore_p4.elf';obj=root/'build/rts-worker-p4/hook7.bin'
subprocess.run([prefix+'objcopy','--dump-section','patch_rts7='+str(obj),str(elf)],check=True)
loader={p[2]:int(p[0],16) for l in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=l.split())==3}
hook=0x0380bfa4
def model7():
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a,n in [(0x02000000,0x400000),(0x03000000,0x800000),(0x03800000,0x10000),(0x04000000,0x2000),(0x04100000,0x1000)]:u.mem_map(a,n)
 u.mem_write(base,b'\0'*meta['memory_bytes']);u.mem_write(base,bytes(image));u.mem_write(hook,obj.read_bytes());u.mem_write(0x04000241,b'\x03');half(u,0x04000184,0x8100)
 names={'rts7_diagnostic_address':syms['gRtsM2']+28,'rts7_read_busy_address':0x0380bda4,'rts7_write_busy_address':0x0380bdf0,'rts7_clock_address':syms['gRtsM2Frames'],'rts7_mailbox_address':syms['gRtsArm7Mailbox'],'rts7_capture_address':syms['rtsArm7CaptureContext'],'rts7_service_address':syms['rtsArm7CaptureService'],'rts7_operation_address':syms['gRtsP4']+4,'rts7_begin_address':syms['rtsP4Arm7Begin']|1,'rts7_loop_address':syms['rtsP4Arm7Entry']}
 for name,val in names.items():put(u,hook+loader[name]-loader['__start_patch_rts7'],val)
 return u
for mask in (0x381,0x382):
 u=model7();done=0x03809000;state={'own':0,'peer':0,'line':192,'park':False,'ticks':0,'entered':False};sp=0x0380f000
 def read(cpu,ac,a,n,v,d):
  if a==0x04000130:half(cpu,a,0x3ff^mask)
  elif a==0x04000180:half(cpu,a,(state['own']<<8)|state['peer'])
  elif a==0x04000006:
   state['line']=(state['line']+17)%263;half(cpu,a,state['line']);state['ticks']+=1
   if state['park'] and state['ticks']>80:state['peer']=13
 def write(cpu,ac,a,n,v,d):
  if a==0x04000180:
   state['own']=(v>>8)&15
   if state['own']==11:state['peer']=10
   if state['own']==12:state['park']=True
 def enter(cpu,a,n,d):state['entered']=True;assert syms['gRtsP4Arm7Stack']<=cpu.reg_read(UC_ARM_REG_SP)<=syms['gRtsP4Arm7Stack']+512
 u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100003);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.hook_add(UC_HOOK_CODE,enter,begin=syms['rtsP4Arm7Loop'],end=syms['rtsP4Arm7Loop'])
 for i in range(31):
  u.reg_write(UC_ARM_REG_CPSR,0x60000092);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_SPSR,0x1f);put(u,sp,0,done)
  for j,reg in enumerate(REGS[2:]):u.reg_write(reg,0x12340000+j)
  u.emu_start(hook,done,count=1000000);assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_SP)==sp+8
  assert [u.reg_read(x) for x in REGS[2:]]==[0x12340000+j for j in range(11)]
 assert state['entered'] and state['park'];assert get(u,syms['gRtsP4']+4)==(mask==0x382)
 assert u.reg_read(UC_ARM_REG_CPSR)==0x60000092
 print('PASS actual ARM7 VBlank hotkey',hex(mask),'-> own main-RAM stack, clock, normal release, exact private epilogue ABI')
# Destructive RPC path: consume actual commands 2/3/4/5 and return directly into
# the saved IRQ. This must never unwind through a private WRAM stack.
u=model7();mail=syms['gRtsArm7Mailbox'];ctrl=syms['gRtsP4'];scratch=syms['gRtsP4Scratch'];ctx=capture[512+0x40c000:512+0x40c200];c=words(ctx)
u.mem_write(0x03800000,capture[512+0x40c200:512+0x41c200]);u.mem_write(0x03000000,capture[512+0x41c200:512+0x424200]);u.mem_write(0x037f8000,capture[512+0x41c200:512+0x424200]);u.mem_write(mail+544,ctx)
put(u,mail+32,*([0xdeadbeef]*128));put(u,scratch,0x31525341,1,0x807f,512,0,0);put(u,ctrl+128,1,0x11223344)
put(u,syms['gRtsSoundShadow']+400+16*4,0x0200807f) # master/bias packed
put(u,mail,2,1,0,0,0)
state={'line':192,'next':0,'sent':[],'ready':False};commands=[3,4,5]
def read(cpu,ac,a,n,v,d):
 if a==0x04000180:half(cpu,a,10)
 elif a==0x04000006:state['line']=(state['line']+17)%263;half(cpu,a,state['line'])
 elif a==0x04000184:half(cpu,a,0x8100)
 elif a==mail:
  if get(cpu,mail+4)==get(cpu,mail+8) and state['next']<len(commands):
   command=commands[state['next']];state['next']+=1;put(cpu,mail,command,state['next']+1)
 elif a==ctrl+12 and state['ready']:put(cpu,a,1)
def write(cpu,ac,a,n,v,d):
 if a==0x04000188:state['sent'].append(v)
 elif a==ctrl+8 and v==1:state['ready']=True
 if 0x03000000<=a<0x03008000:cpu.mem_write(0x037f8000+(a&32767),v.to_bytes(n,'little'))
u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100003);u.hook_add(UC_HOOK_MEM_READ,read,begin=mail,end=mail+19);u.hook_add(UC_HOOK_MEM_READ,read,begin=ctrl+12,end=ctrl+15);u.hook_add(UC_HOOK_MEM_WRITE,write)
u.reg_write(UC_ARM_REG_CPSR,0xd2);u.reg_write(UC_ARM_REG_SP,0x0380f000);u.reg_write(UC_ARM_REG_LR,0x03809000)
u.emu_start(syms['rtsP4Arm7Entry'],c[19]&~1,count=200000)
assert u.reg_read(UC_ARM_REG_PC)==c[19]&~1 and state['ready'] and state['next']==3 and state['sent']==[0x11223344]
assert bytes(u.mem_read(0x03800000,512))==struct.pack('<128I',*([0xdeadbeef]*128))
assert u.reg_read(UC_ARM_REG_SP)==c[2]+48 and u.reg_read(UC_ARM_REG_CPSR)==c[3]
print('PASS actual ARM7 RPC 2/3/4/5: private sector write, FIFO/audio preparation, coherent release -> saved IRQ without private-stack return')
