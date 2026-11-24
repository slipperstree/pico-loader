"""Execute P4's real private VBlank hook and main-RAM ARM7 RPC loop."""
from pathlib import Path
import sys,subprocess,struct,os
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import *
root=Path(sys.argv[1]).resolve();model=Path(__file__).with_name('test_rts_p4_worker.py')
exec(compile(model.read_text().split('disk={physical[0]:bytes(blank)}')[0],str(model),'exec'),globals())
elf=root/('build/picoLoader9_DSPICO_trace_p43.elf' if TRACE else 'build/picoLoader9_DSPICO_restore_p4.elf');obj=f/'hook7.bin'
subprocess.run([prefix+'objcopy','--dump-section','patch_rts7='+str(obj),str(elf)],check=True)
loader={p[2]:int(p[0],16) for l in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=l.split())==3}
hook=0x0380bfa4
def model7():
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for a,n in [(0x02000000,0x400000),(0x03000000,0x800000),(0x03800000,0x10000),(0x04000000,0x2000),(0x04100000,0x1000)]:u.mem_map(a,n)
 u.mem_write(base,b'\0'*meta['memory_bytes']);u.mem_write(base,bytes(image));u.mem_write(hook,obj.read_bytes());u.mem_write(0x04000241,b'\x03');half(u,0x04000184,0x8100)
 names={'rts7_diagnostic_address':syms['gRtsM2']+28,'rts7_read_busy_address':0x0380bda4,'rts7_write_busy_address':0x0380bdf0,'rts7_clock_address':syms['gRtsM2Frames'],'rts7_mailbox_address':syms['gRtsArm7Mailbox'],'rts7_capture_address':syms['rtsArm7CaptureContext'],'rts7_service_address':syms['rtsArm7CaptureService'],'rts7_operation_address':syms['gRtsP4']+4,'rts7_begin_address':syms['rtsP4Arm7Begin']|1,'rts7_loop_address':syms['rtsP4Arm7Entry']}
 for name,val in names.items():put(u,hook+loader[name]-loader['__start_patch_rts7'],val)
 return u
for mask,cancel in ((0x381,False),(0x382,False),(0x381,True)):
 u=model7();done=0x03809000;
 if cancel:put(u,hook+loader['rts7_spin_budget']-loader['__start_patch_rts7'],32)
 state={'own':0,'peer':0,'line':192,'park':False,'ticks':0,'entered':False,'checkpoints':[],'private_ack':False,'private_reads':0};sp=0x0380f000
 def read(cpu,ac,a,n,v,d):
  if a==0x04000130:half(cpu,a,0x3ff^mask)
  elif a==0x04000180:
   if TRACE and state['private_ack']:
    state['private_reads']+=1;state['peer']=13 if state['private_reads']<=4 else 0
   elif cancel and state['park']:
    state['ticks']+=1;state['peer']=13 if state['ticks']>240 else 9+(state['ticks']//4)%2
   half(cpu,a,(state['own']<<8)|state['peer'])
  elif a==0x04000006:
   state['line']=(state['line']+17)%263;half(cpu,a,state['line']);state['ticks']+=1
   if state['park'] and state['ticks']>80:state['peer']=13
 def write(cpu,ac,a,n,v,d):
  if base<=a<limit and not state['park']:
   assert a==syms['gRtsM2']+28,'New main-RAM work occurred before ARM9 ACK/C'
  if a==0x04000180:
   state['own']=(v>>8)&15
   if TRACE and 1<=state['own']<=10:state['checkpoints'].append(state['own'])
   if TRACE and state['own']==0 and state['park']:state['private_ack']=True
   if state['own']==11:state['peer']=10
   if state['own']==12:
    assert get(cpu,syms['gRtsArm7Mailbox']+544)==0,'Capture ran before C/visible ARM9 phase'
    state['park']=True;state['peer']=10 if cancel else 8
 def enter(cpu,a,n,d):state['entered']=True;assert syms['gRtsP4Arm7Stack']<=cpu.reg_read(UC_ARM_REG_SP)<=syms['gRtsP4Arm7Stack']+meta['arm7_stack_bytes']
 u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100003);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.hook_add(UC_HOOK_CODE,enter,begin=syms['rtsP4Arm7Loop'],end=syms['rtsP4Arm7Loop'])
 for i in range(31):
  u.reg_write(UC_ARM_REG_CPSR,0x60000092);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_SPSR,0x1f);put(u,sp,0,done)
  for j,reg in enumerate(REGS[2:]):u.reg_write(reg,0x12340000+j)
  u.emu_start(hook,done,count=1000000);assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_SP)==sp+8
  assert [u.reg_read(x) for x in REGS[2:]]==[0x12340000+j for j in range(11)]
 assert state['park'] and state['entered']==(not cancel)
 if TRACE:assert state['private_ack'] and state['private_reads']>=5,'Did not wait in private WRAM for ARM9 release'
 if not cancel:
  assert get(u,syms['gRtsP4']+4)==(mask==0x382)
  if TRACE:assert state['checkpoints']==list(range(1,11)),state['checkpoints']
 else:assert get(u,syms['gRtsArm7Mailbox']+544)==0
 assert u.reg_read(UC_ARM_REG_CPSR)==0x60000092
 print('PASS actual ARM7 VBlank hotkey',hex(mask),'cancel before start' if cancel else 'start accepted','-> own main-RAM stack, clock, normal release, exact private epilogue ABI')
# Destructive RPC path: consume actual commands 2/3/4/5 and return directly into
# the saved IRQ. This must never unwind through a private WRAM stack.
u=model7();mail=syms['gRtsArm7Mailbox'];ctrl=syms['gRtsP4'];scratch=syms['gRtsP4Scratch'];ctx=capture[512+0x40c000:512+0x40c200];c=words(ctx)
u.mem_write(0x03800000,capture[512+0x40c200:512+0x41c200]);u.mem_write(0x03000000,capture[512+0x41c200:512+0x424200]);u.mem_write(0x037f8000,capture[512+0x41c200:512+0x424200]);u.mem_write(mail+544,ctx)
put(u,mail+32,*([0xdeadbeef]*128));put(u,scratch,0x31525341,1,0x807f,512,0,0);put(u,ctrl+128,1,0x11223344)
put(u,syms['gRtsSoundShadow']+400+16*4,0x0200807f) # master/bias packed
put(u,mail,1,1,0,0,0)
state={'line':192,'next':0,'sent':[],'ready':False,'lowest_sp':syms['gRtsP4Arm7Stack']+meta['arm7_stack_bytes']};commands=[2,3,4,5]
def read(cpu,ac,a,n,v,d):
 if a==0x04000180:half(cpu,a,10)
 elif a==0x04000006:state['line']=(state['line']+17)%263;half(cpu,a,state['line'])
 elif a==0x04000184:half(cpu,a,0x8100)
 elif a==mail:
  if get(cpu,mail+4)==get(cpu,mail+8) and state['next']<len(commands):
   command=commands[state['next']];state['next']+=1;put(cpu,mail,command,state['next']+1)
   if command==2:put(cpu,mail+32,*([0xdeadbeef]*128))
 elif a==ctrl+12 and state['ready']:put(cpu,a,1)
def write(cpu,ac,a,n,v,d):
 sp=cpu.reg_read(UC_ARM_REG_SP)
 if base<=sp<limit:
  state['lowest_sp']=min(state['lowest_sp'],sp)
  assert sp>=syms['gRtsP4Arm7Stack'],'ARM7 main stack overflow'
 if a==0x04000188:state['sent'].append(v)
 elif a==ctrl+8 and v==1:state['ready']=True
 if 0x03000000<=a<0x03008000:cpu.mem_write(0x037f8000+(a&32767),v.to_bytes(n,'little'))
u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100003);u.hook_add(UC_HOOK_MEM_READ,read,begin=mail,end=mail+19);u.hook_add(UC_HOOK_MEM_READ,read,begin=ctrl+12,end=ctrl+15);u.hook_add(UC_HOOK_MEM_WRITE,write)
for i,mode in enumerate((31,18,19,23,27,17)):
 u.reg_write(UC_ARM_REG_CPSR,0xc0|mode);u.reg_write(UC_ARM_REG_SP,c[20+i*3]);u.reg_write(UC_ARM_REG_LR,c[21+i*3])
 if mode!=31:u.reg_write(UC_ARM_REG_SPSR,c[22+i*3])
 if mode==17:
  for reg,value in zip(REGS[8:],c[38:43]):u.reg_write(reg,value)
u.reg_write(UC_ARM_REG_CPSR,0xd2);u.reg_write(UC_ARM_REG_SP,0x0380f000);u.reg_write(UC_ARM_REG_LR,0x03809000)
for reg,value in zip(REGS,[0x4000,c[2],c[3],1,0]):u.reg_write(reg,value)
def assertArm(cpu,a,n,d):
 assert not cpu.reg_read(UC_ARM_REG_CPSR)&32,'ARM7 capture service entered in Thumb mode'
u.hook_add(UC_HOOK_CODE,assertArm,begin=syms['rtsArm7CaptureService'],end=syms['rtsArm7CaptureService'])
u.emu_start(syms['rtsP4Arm7Entry'],c[19]&~1,count=200000)
assert u.reg_read(UC_ARM_REG_PC)==c[19]&~1 and state['ready'] and state['next']==4 and state['sent']==[0x11223344]
assert bytes(u.mem_read(0x03800000,512))==struct.pack('<128I',*([0xdeadbeef]*128))
assert get(u,mail+544+92)==c[2],'Scratch IRQ stack leaked into saved game context'
assert u.reg_read(UC_ARM_REG_SP)==c[2]+48 and u.reg_read(UC_ARM_REG_CPSR)==c[3]
print('PASS actual ARM7 RPC 1/2/3/4/5: private sector write, FIFO/audio preparation, coherent release -> saved IRQ without private-stack return')

print("ARM7 maximum observed stack:",syms["gRtsP4Arm7Stack"]+meta["arm7_stack_bytes"]-state["lowest_sp"],"/",meta["arm7_stack_bytes"])
