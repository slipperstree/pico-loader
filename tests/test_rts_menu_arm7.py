"""Execute ARM7 RTC GPIO and menu mute/clock/unmute commands in Unicorn.
GPIO transitions are modeled; this does not validate the physical RTC timing.
"""
from pathlib import Path
import json,os,struct,subprocess,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();f=r/'build/rts-worker-p6'
prefix=os.environ.get('ARM_NONE_EABI_PREFIX','C:/msys64/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-' if os.name=='nt' else 'arm-none-eabi-')
symbols={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(f/'worker.elf')],text=True).splitlines() if len(p:=line.split())==3}
def put(u,a,value,n=4):u.mem_write(a,value.to_bytes(n,'little'))
def get(u,a,n=4):return int.from_bytes(u.mem_read(a,n),'little')
def run(status=2,hour=0x16,invalid=False,server=False):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for address,size in ((0x02200000,0x10000),(0x03800000,0x10000),(0x04000000,0x2000)):
  u.mem_map(address,size)
 u.mem_write(0x02200000,(f/'worker.bin').read_bytes())
 put(u,0x04000134,0x1122,2);put(u,0x04000138,0x8072,2)
 data=[0x26,0 if invalid else 0x11,0x24,0, hour,0x23,0x45]
 gpio={'value':0x8072,'command':0,'bits':0,'queue':[],'commands':[],'peer':8,'completed':[],'mute':[],'done':False}
 def read(cpu,access,a,n,value,user):
  if a==0x04000138:
   pins=gpio['value'];bit=gpio['queue'][0] if gpio['queue'] and not pins&16 else pins&1
   put(cpu,a,(pins&~1)|bit,2)
  elif a==0x04000180:put(cpu,a,gpio['peer'],2)
  elif a==0x04000006:put(cpu,a,(get(cpu,a,2)+17)%263,2)
 def write(cpu,access,a,n,value,user):
  if a==0x04000138:
   old=gpio['value'];gpio['value']=value
   if value&4 and not old&4:gpio['command']=0;gpio['bits']=0;gpio['queue']=[]
   if value&4 and value&2 and not old&2:
    if value&16:
     gpio['command']|=(value&1)<<gpio['bits'];gpio['bits']+=1
     if gpio['bits']==8:
      command=gpio['command'];gpio['commands'].append(command);raw=[status] if command==0x86 else data if command==0xa6 else []
      assert raw,hex(command);gpio['queue']=[(byte>>i)&1 for byte in raw for i in range(8)]
    elif gpio['queue']:gpio['queue'].pop(0)
  elif a==0x04000500:gpio['mute'].append(value)
  elif server and a==mail+8:
   gpio['completed'].append(value)
   if value==1:put(cpu,mail,8);put(cpu,mail+4,2)
   elif value==2:put(cpu,mail,7);put(cpu,mail+4,3)
   elif value==3:gpio['peer']=13
 u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
 done=0x0220ff00
 def finish(cpu,a,n,user):gpio['done']=True;cpu.emu_stop()
 u.hook_add(UC_HOOK_CODE,finish,begin=done,end=done)
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,0x0380f000);u.reg_write(UC_ARM_REG_LR,done)
 if server:
  mail=symbols['gRtsArm7Mailbox'];out=mail+32
  put(u,0x04000184,0x8100,2);put(u,0x04000500,0x807f,2)
  put(u,mail,6);put(u,mail+4,1)
  u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_R1,0)
  entry=symbols['rtsP4Arm7Loop']
 else:
  out=0x0220f000;u.reg_write(UC_ARM_REG_R0,out);entry=symbols['RtsMenuReadClock7']
 u.emu_start(entry|1,0,count=1_000_000)
 assert gpio['done'];assert get(u,0x04000134,2)==0x1122 and get(u,0x04000138,2)==0x8072
 expected_hour=16 if status&2 else (0 if hour&0x3f==0x12 else (hour&15))+(12 if hour&0x40 else 0)
 assert bytes(u.mem_read(out,8))==struct.pack('<H6B',0 if invalid else 2026,0 if invalid else 11,24,expected_hour,23,45,0)
 assert gpio['commands']==[0x86,0xa6],gpio
 if server:assert gpio['completed']==[1,2,3] and gpio['mute']==[0x7f,0x807f],gpio
for status,hour in ((2,0x16),(0,0x12),(0,0x52),(0,0x41),(0,0x01)):run(status,hour)
run(invalid=True);run(server=True)
(f/'menu-arm7-results.json').write_text(json.dumps({'rtc_gpio_24h_and_12h':'PASS','invalid_clock':'PASS','gpio_state_restored':'PASS','actual_server_mute_clock_unmute':'PASS','physical_hardware':False},indent=2))
print('PASS actual ARM7 RTC GPIO (24h/AM/PM), restored pin state, invalid time and server mute/clock/unmute')
