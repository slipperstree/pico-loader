"""Local full P4 ARM9 worker with actual ARM7 sector/audio/continuation helpers.
Uses an independently supplied private M3.2 capture; never packages its bytes.
The two physical SD/FIFO interfaces are models, not DSPico hardware.
"""
import hashlib,json,os,struct,subprocess,sys,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_INVALID
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();capture=Path(sys.argv[2]).read_bytes();h0=struct.unpack('<128I',capture[:512]);TRACE='--p43' in sys.argv;f=r/('build/rts-worker-p43' if TRACE else 'build/rts-worker-p4')
meta=json.loads((f/'RtsM2Image.json').read_text());original=(f/'worker.bin').read_bytes();base=0x023fa000;limit=base+meta['memory_bytes'];assert limit<=0x023ff000
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful'))/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
syms={p[2]:int(p[0],16)-meta['link_base']+base for l in subprocess.check_output([prefix+'nm',str(f/'worker.elf')],text=True).splitlines() if len(p:=l.split())==3}
image=bytearray(original)
for off in meta['relocations']:struct.pack_into('<I',image,off,(struct.unpack_from('<I',image,off)[0]+base-meta['link_base'])&0xffffffff)
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
cpkeys=[(1,0,0),(2,0,0),(2,0,1),(3,0,0),(5,0,2),(5,0,3)]+[(6,i,0) for i in range(8)]+[(9,1,0),(9,1,1),(9,0,0),(9,0,1),(13,0,1)]
cpvalues=[h0[14],0x42,h0[40],h0[41],0x15111011,0x55111111,0x04000033,0x0200002b,h0[38],0x08000035,0x027c001b,0x0100002f,0xffff001d,0x027ff017,h0[15],h0[16],0,0,0x1234]
def words(b):return struct.unpack('<'+'I'*(len(b)//4),b)
def put(u,a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def half(u,a,v):u.mem_write(a,struct.pack('<H',v))
snapshotbytes=0x4c9800;sectors=snapshotbytes//512
extents=[(4096,0x1000),(4096,0x3000),(sectors-8192,0x7000)];physical=[a+i for n,a in extents for i in range(n)]
blank=bytearray(512);struct.pack_into('<6I',blank,0,0x30505452,0x40001,snapshotbytes,0x4a473241,0,0x4c9600)
def make(disk,load=False,mutate=False,corrupt=False,identity=False,partial=False,empty=False,arm7_unready=False,early_refusal=False,ipc_unlatched=False,release_unready=False,refusal=None,source_alias=False,psg_first=False):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_946);a7=Uc(UC_ARCH_ARM,UC_MODE_ARM);a7.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for a,n in [(0x02000000,0x400000),(h0[10],0x4000),(0x01ff8000,0x8000),(0x04000000,0x2000),(0x04100000,0x1000),(0x06800000,0xa4000),(0x05000000,0x1000),(0x07000000,0x1000)]:u.mem_map(a,n)
 for a,n in [(0x02000000,0x400000),(0x03000000,0x800000),(0x03800000,0x10000),(0x04000000,0x2000),(0x04100000,0x1000)]:a7.mem_map(a,n)
 for cpu in (u,a7):cpu.mem_write(0x02000000,capture[512:512+0x400000]);cpu.mem_write(base,b'\0'*meta['memory_bytes']);cpu.mem_write(base,bytes(image))
 u.mem_write(h0[10],capture[512+0x400000:512+0x404000]);u.mem_write(0x01ff8000,capture[512+0x404000:512+0x40c000])
 private=capture[512+0x40c200:512+0x41c200];shared=capture[512+0x41c200:512+0x424200]
 a7.mem_write(0x03800000,private);a7.mem_write(0x03000000,shared);a7.mem_write(0x037f8000,shared)
 video=capture[512+0x424200:512+0x424400];v=words(video);vc=[0x04000240,0x04000241,0x04000242,0x04000243,0x04000244,0x04000245,0x04000246,0x04000248,0x04000249]
 for a,b in zip(vc,v[9:18]):u.mem_write(a,bytes([b]))
 for a,b in [(0x04000000,v[5]),(0x04001000,v[6])]:put(u,a,b)
 for a,b in [(0x0400006c,v[7]),(0x0400106c,v[8]),(0x04000304,v[18])]:half(u,a,b)
 u.mem_write(0x04000247,b'\x03');a7.mem_write(0x04000241,b'\x03')
 for i in range(8):half(u,0x04000008+(i&3)*2+(0x1000 if i>=4 else 0),v[20+i])
 targetvideo=capture[512+0x424400:512+0x4c9400];u.mem_write(0x06800000,targetvideo[:0xa4000]);u.mem_write(0x05000000,targetvideo[0xa4000:0xa4800]);u.mem_write(0x07000000,targetvideo[0xa4800:])
 cfg=syms['gRtsM2'];mail=syms['gRtsArm7Mailbox'];ctrl=syms['gRtsP4'];shadow=syms['gRtsSoundShadow'];stack=syms['gRtsM2Stack'];a7stack=syms['gRtsP4Arm7Stack']
 config=[0x30505452,0x40001,sectors,len(extents),0x800,0x10000,0x4a473241,0]
 for n,a in extents:config.extend((n,a))
 config+=[0]*(72-len(config));put(u,cfg,*config,base,meta['memory_bytes']);put(u,cfg+296+76,6)
 if early_refusal:put(u,cfg+36,0x400)
 if refusal=='sd_busy':put(u,cfg+28,4096)
 for cpu in (u,a7):
  cpu.mem_write(mail+544,capture[512+0x40c000:512+0x40c200]);cpu.mem_write(syms['gRtsP4Identity'],bytes.fromhex('078631bbdc625a13340b961ea902b9475b7efbc2869ddbbde5999638f47d5eb4')+bytes.fromhex(meta['p4_build_fingerprint'])+b'\0'*16)
  put(cpu,shadow,0x31485341,1,1,0)
  put(cpu,shadow+16,0x8800407f,0x02710000 if source_alias else 0x02010000,65000,4,16);put(cpu,shadow+336,0xfff0)
  if refusal=='sound_busy':put(cpu,syms['gRtsSoundBusy'],1)
  if refusal=='sound_coverage':put(cpu,shadow+336,0)
  if refusal=='sound_unsupported':put(cpu,shadow+12,1)
  if refusal=='sound_range':put(cpu,shadow+20,0x04000400)
 put(u,syms['gRtsP4TailAddress'],0x02000210)
 # Tail stays part of the captured main RAM, outside the protected work arena.
 tail=syms['rtsArm9RestoreTail'];u.mem_write(0x02000210,bytes(u.mem_read(tail,80)))
 # The source capture's secure gate/stub may share this interval. Assert it doesn't.
 pc=h0[34]&~1;assert not 0x02000210<=pc<0x02000260,hex(pc)
 frame=h0[37];entry=frame-56;entryregs=words(bytes(u.mem_read(entry,56)))
 # Source and fixture target use the same original saved gate ABI.
 put(u,ctrl+4,int(load));put(a7,ctrl+4,int(load))
 fifo9=[0x12345678,0x55aa55aa];fifo7=[0x90001234]
 state={'server7':False,'exmem_writes':[],'mode':'idle','word':0,'sector':0,'readsector':0,'own':10,'peer':12,'polls':0,'vcount':192,'frames':0,'fault':None,'done':False,'stages':[],'writes':0,'rpc':[],'minsp9':stack+1024,'minsp7':a7stack+meta['arm7_stack_bytes'],'restored':False,'cpclosed':False,'readcount':0}
 cp=dict(zip(cpkeys,cpvalues));cp[(6,2,0)]=0
 if mutate:
  u.mem_write(0x02030000,b'changed progress'*30);u.mem_write(0x06810000,b'\xcc'*512);a7.mem_write(0x03800100,b'\xdd'*512)
 if identity:u.mem_write(syms['gRtsP4Identity'],b'X'*32)
 half(u,0x04000204,h0[39]);half(u,0x040001a0,0x8000)
 for cpu in (u,a7):
  put(cpu,0x04000208,0);put(cpu,0x04000210,0x1040001);put(cpu,0x04000214,1)
  for i in range(4):half(cpu,0x04000102+i*4,0)
 half(a7,0x04000500,0x807f);half(a7,0x04000504,512);put(a7,0x04000400,0x8800407f)
 if psg_first:put(a7,0x040004b0,0xe3400301)
 def a7read(cpu,ac,a,n,val,d):
  if a==0x04000184:half(cpu,a,0x8000|(0x4000 if refusal=='fifo7_error' else 0)|(0x100 if not fifo7 else 0)|(2 if len(fifo9)==16 else 0))
  elif a==0x04100000:put(cpu,a,fifo7.pop(0))
 def a7write(cpu,ac,a,n,val,d):
  if a==0x04000188:fifo9.append(val)
  if 0x03000000<=a<0x03008000:cpu.mem_write(0x037f8000+(a&32767),val.to_bytes(n,'little'))
 a7.hook_add(UC_HOOK_MEM_READ,a7read,begin=0x04000000,end=0x04100003);a7.hook_add(UC_HOOK_MEM_WRITE,a7write)
 done7=0x020f0000
 def call7(name,args,thumb=False):
  a7.reg_write(UC_ARM_REG_CPSR,0xd2 if name=='rtsEnterArm7Continuation' else 0xdf);a7.reg_write(UC_ARM_REG_SP,a7stack+meta['arm7_stack_bytes']);a7.reg_write(UC_ARM_REG_LR,done7)
  for reg,val in zip(REGS,args):a7.reg_write(reg,val)
  end=(words(bytes(a7.mem_read(mail+544,512)))[19]&~1) if name=='rtsEnterArm7Continuation' else done7
  try:a7.emu_start(syms[name]|int(thumb),end,count=100000)
  except Exception as e:raise AssertionError(('ARM7',name,hex(a7.reg_read(UC_ARM_REG_PC)),hex(a7.reg_read(UC_ARM_REG_SP)),hex(end))) from e
  assert a7.reg_read(UC_ARM_REG_PC)==end,(name,hex(a7.reg_read(UC_ARM_REG_PC)),hex(end))
 def sync7():
  # ARM7 sees shared main memory, with an independent CPU register bank/MMIO.
  a7.mem_write(base,bytes(u.mem_read(base,meta['memory_bytes'])))
 def rpc(cpu,ac,a,n,val,d):
  command,req,completed,status,block=words(bytes(cpu.mem_read(mail,20)))
  if not command or req==completed:return
  state['rpc'].append(command);sync7()
  if command==1:
   call7('rtsArm7CaptureService',[mail]);cpu.mem_write(mail,bytes(a7.mem_read(mail,544)));return
  if command==2:
   call7('rtsArm7RestoreSector',[block,mail+32]);assert a7.reg_read(UC_ARM_REG_R0)==1
  elif command==3:
   count=get(cpu,ctrl+128)
   for x in words(bytes(cpu.mem_read(ctrl+132,count*4))):fifo9.append(x)
  elif command==4:call7('RtsPrepareSoundRestart',[syms['gRtsP4Scratch'],syms['mmio']|1,0],True)
  elif command==5:put(cpu,ctrl+8,1)
  else:raise AssertionError(command)
  put(cpu,mail+12,0);put(cpu,mail+8,req)
 u.hook_add(UC_HOOK_MEM_READ,rpc,begin=mail+8,end=mail+11)
 # ARM7 preparation is now triggered by ARM9's explicit start nibble 8,
 # after visible feedback and D-cache off. No FIFO/audio work happens here.
 cache={'after_clean':False,'dirty':{},'transitions':0,'waiting':False}
 def coproc(cpu,a,n,d):
  if cpu.reg_read(UC_ARM_REG_CPSR)&32:return
  assert not cache['waiting'],'Cache maintenance executed during cache-off ARM7 wait'
  ins=get(cpu,a);key=((ins>>16)&15,ins&15,(ins>>5)&7);rd=(ins>>12)&15
  cpreg=(REGS+[UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC])[rd]
  if ins&(1<<20):cpu.reg_write(cpreg,cp[key])
  else:
   value=cpu.reg_read(cpreg)
   if '--cache-check' in sys.argv:
    if key==(7,14,2) and value==0xc00003e0:cache['after_clean']=True;cache['dirty']={}
    if key==(1,0,0) and cp[key]&4 and not value&4:
     scratch=cfg+296+512+192
     essential=[a for a in cache['dirty'] if not scratch<=a<scratch+44]
     assert not essential,('Dirty RAM/stack stores after final cache clean',list(map(hex,essential[:12])))
     for address,byte in cache['dirty'].items():cpu.mem_write(address,bytes([byte]))
     cache['transitions']+=1;cache['after_clean']=False
   if key[0]!=7:cp[key]=value
   if key==(6,2,0) and cp[key]&1:assert a<0x02000800;state['cpclosed']=True
  cpu.reg_write(UC_ARM_REG_PC,a+4)
 # CP15 instructions only occur in ARM sections and the copied secure tail.
 for off in range(0,len(image)-3,4):
  ins=struct.unpack_from('<I',image,off)[0]
  if ins&0x0f000f10==0x0e000f10:u.hook_add(UC_HOOK_CODE,coproc,begin=base+off,end=base+off)
 for off in range(0,80,4):
  if get(u,0x02000210+off)&0x0f000f10==0x0e000f10:u.hook_add(UC_HOOK_CODE,coproc,begin=0x02000210+off,end=0x02000210+off)
 def read(cpu,ac,a,n,val,d):
  if a==0x04000184:half(cpu,a,0x8000|(0x4000 if refusal=='fifo9_error' else 0)|(0x100 if not fifo9 else 0)|(2 if len(fifo7)==16 else 0))
  elif a==0x04100000:put(cpu,a,fifo9.pop(0))
  elif a==0x04000006:
   state['vcount']=(state['vcount']+17)%263;state['frames']+=1;half(cpu,a,state['vcount'])
  elif a==0x04000130:half(cpu,a,0x3fd if state['frames']%8>=4 else 0x3ff)
  elif a==0x04000180:half(cpu,a,0x4000|(state['own']<<8)|state['peer'])
  elif a==0x040001a4:
   state['polls']+=1;put(cpu,a,0x80800000 if state['mode'] in ('write','read','poll') else 0)
  elif a==0x04100010:
   if state['mode']=='poll':value=1;state['mode']='idle'
   else:
    assert state['mode']=='read';data=disk.get(state['readsector'],b'\0'*512);value=struct.unpack_from('<I',data,state['word']*4)[0]
    if corrupt and state['readsector']==physical[33] and state['word']==0:value^=1
    state['word']+=1
    if state['word']==128:state['mode']='idle';state['readcount']+=1
   put(cpu,a,value)
 u.hook_add(UC_HOOK_MEM_READ,read,begin=0x04000000,end=0x04100013)
 def clock(cpu,ac,a,n,val,d):put(cpu,a,state['polls']//4096)
 u.hook_add(UC_HOOK_MEM_READ,clock,begin=syms['gRtsM2Frames'],end=syms['gRtsM2Frames']+3)
 def write(cpu,ac,a,n,val,d):
  if '--cache-check' in sys.argv and cache['after_clean'] and cp[(1,0,0)]&4 and 0x02000000<=a<0x02400000:
   before=bytes(cpu.mem_read(a,n))
   for i,byte in enumerate(before):cache['dirty'].setdefault(a+i,byte)
  spNow=cpu.reg_read(UC_ARM_REG_SP)
  if stack<=spNow<=stack+1024:state['minsp9']=min(state['minsp9'],spNow)
  if a==0x04000204:state['exmem_writes'].append((val,state['server7']))
  if a==0x04000188:fifo7.append(val)
  elif a==0x04000180:
   state['own']=(val>>8)&15
   if ipc_unlatched and state['own']==8:state['own']=10;return
   if state['own']==8:
    state['server7']=True
    assert not cp[(1,0,0)]&4 and (2,0) in state['stages'],'ARM7 started before visible feedback/cache off'
    if not arm7_unready:
     sync7()
     if psg_first:
      put(a7,a7stack,0x040004b0,0x10000-777)
      call7('rtsSoundObserveReload',[a7stack],True)
     call7('rtsP4Arm7Begin',[0x4000],True)
     cpu.mem_write(ctrl,bytes(a7.mem_read(ctrl,224)));put(cpu,ctrl+4,int(load));put(cpu,ctrl+8,1)
     cpu.mem_write(shadow,bytes(a7.mem_read(shadow,512)))
   elif state['own']==13:
    if release_unready:state['peer']=10
    else:state['peer']=0;state['server7']=False
   elif state['own']==14:state['fault']=get(cpu,cfg+296+72);cpu.emu_stop()
  elif a==0x040001a4 and val&0x80000000:
   assert not cp[(1,0,0)]&4
   cmd=bytes(cpu.mem_read(0x040001a8,8));op=cmd[0];arg=int.from_bytes(cmd[4:],'big')
   if op==0xe3:assert arg in physical;state['readsector']=arg;state['mode']='idle'
   elif op==0xe4:state['mode']='poll'
   elif op==0xe5:state['mode']='read';state['word']=0
   elif op==0xf6:assert arg in physical;state['sector']=arg;state['mode']='write';state['word']=0;state['buffer']=bytearray()
   else:raise AssertionError(op)
  elif a==0x04100010:
   assert state['mode']=='write';state['buffer']+=struct.pack('<I',val);state['word']+=1
   if state['word']==128:disk[state['sector']]=bytes(state['buffer']);state['mode']='idle';state['writes']+=1
  elif a==ctrl+12 and val==1:
   state['restored']=True;sync7();call7('RtsReleaseSoundRestart',[syms['gRtsP4Scratch'],syms['mmio']|1,0],True);call7('rtsEnterArm7Continuation',[mail+544])
  if 0x02000000<=a<0x02400000 and not base<=a<limit:
   assert load and state['readcount']>=sectors,('Destructive write before validation',hex(a),state['readcount'])
 u.hook_add(UC_HOOK_MEM_WRITE,write)
 if '--bus-check' in sys.argv:
  def bus(cpu,ac,a,n,val,d):
   exmem=struct.unpack('<H',cpu.mem_read(0x04000204,2))[0]
   assert not (state['server7'] and exmem&0x8000),('ARM9 shared main RAM access with ARM7 priority/server running',hex(a),hex(exmem),hex(cpu.reg_read(UC_ARM_REG_PC)))
  u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,bus,begin=0x02000000,end=0x023fffff)
 if '--fast-io' in sys.argv:
  def fileRead(cpu,a,n,d):
   index=cpu.reg_read(UC_ARM_REG_R0);out=cpu.reg_read(UC_ARM_REG_R1)
   if partial and index==34 and state['readcount']>=sectors:
    cpu.reg_write(UC_ARM_REG_R0,0);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR));return
   cpu.mem_write(out,disk.get(physical[index],b'\0'*512));state['readcount']+=1
   if corrupt and index==33:put(cpu,out,get(cpu,out)^1)
   cpu.reg_write(UC_ARM_REG_R0,1);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  def fileWrite(cpu,a,n,d):
   index=cpu.reg_read(UC_ARM_REG_R0);src=cpu.reg_read(UC_ARM_REG_R1)
   disk[physical[index]]=bytes(cpu.mem_read(src,512));state['writes']+=1
   cpu.reg_write(UC_ARM_REG_R0,1);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,fileRead,begin=syms['readSector'],end=syms['readSector']);u.hook_add(UC_HOOK_CODE,fileWrite,begin=syms['writeSector'],end=syms['writeSector'])
 done9=0x020f0000
 def done(cpu,a,n,d):state['done']=True;cpu.emu_stop()
 u.hook_add(UC_HOOK_CODE,done,begin=done9,end=done9)
 def stage(cpu,a,n,d):
  st,val=cpu.reg_read(UC_ARM_REG_R0),cpu.reg_read(UC_ARM_REG_R1);state['stages'].append((st,val))
  if st==2 and val==40:cache['waiting']=True
  if (st==2 and val==34) or st==9:cache['waiting']=False
 u.hook_add(UC_HOOK_CODE,stage,begin=syms['progress'],end=syms['progress'])
 def resume(cpu,a,n,d):
  if state['restored']:state['done']=True;cpu.emu_stop()
 u.hook_add(UC_HOOK_CODE,resume,begin=pc,end=pc)
 for i,m in enumerate((31,18,19,23,27,17)):
  u.reg_write(UC_ARM_REG_CPSR,0xc0|m);u.reg_write(UC_ARM_REG_SP,h0[10]+0x3000+i*64);u.reg_write(UC_ARM_REG_LR,0x12340000+i*4)
  if m!=31:u.reg_write(UC_ARM_REG_SPSR,0x6000001f)
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,stack+1024);u.reg_write(UC_ARM_REG_LR,done9);u.reg_write(UC_ARM_REG_R0,entry)
 def invalid(cpu,ac,a,n,val,d):raise AssertionError(('invalid',hex(a),n,hex(cpu.reg_read(UC_ARM_REG_PC)),hex(cpu.reg_read(UC_ARM_REG_SP)),hex(cpu.reg_read(UC_ARM_REG_CPSR)),state['stages'][-3:],state['restored']))
 u.hook_add(UC_HOOK_MEM_INVALID,invalid)
 try:u.emu_start(syms['rtsM2Run']|1,0,count=700000000)
 except Exception as e:raise AssertionError(('ARM9',hex(u.reg_read(UC_ARM_REG_PC)),hex(u.reg_read(UC_ARM_REG_SP)),hex(u.reg_read(UC_ARM_REG_CPSR)),state['stages'][-2:],state['restored'],[hex(u.reg_read(x)) for x in REGS])) from e
 if early_refusal:
  assert state['done'] and not state['fault'] and not state['writes'] and not state['readcount'] and not state['rpc']
  assert (8,256) in state['stages'] and 8!=state['own'] and fifo7==[0x90001234] and fifo9==[0x12345678,0x55aa55aa]
  print('PASS refusal before start: no SD, no unstarted FIFO replay, current game resumes',flush=True);return state
 if refusal:
  expected={'sd_busy':4010,'sound_busy':4101,'fifo7_error':4102,'fifo9_error':4201,'sound_unsupported':4303,'sound_coverage':4400,'sound_range':4600}[refusal]
  assert state['done'] and state['fault'] is None and (8,expected) in state['stages'],state['stages']
  assert not state['writes'] and not state['readcount'] and fifo7==[0x90001234] and fifo9==[0x12345678,0x55aa55aa]
  assert struct.unpack('<H',u.mem_read(0x04000204,2))[0]==h0[39]
  assert not state['server7']
  print('PASS detailed refusal',refusal,'-> S8',expected,'fresh B returns, no card writes, FIFO and EXMEM preserved',flush=True);return state
 if release_unready:
  assert state['fault']==8130 and (9,8130) in state['stages'] and not state['done'] and not state['writes']
  assert state['server7'] and not struct.unpack('<H',u.mem_read(0x04000204,2))[0]&0x8800
  print('PASS missing private ARM7 ACK -> visible S9 8130, ARM9 priority retained, no card writes',flush=True);return state
 if ipc_unlatched:
  assert state['fault']==8128 and not state['done'] and not state['writes'] and not state['rpc']
  print('PASS outgoing IPC nibble not latched -> S9 8128 before ARM7 wait or card I/O',flush=True);return state
 if arm7_unready:
  assert state['fault']==(8112 if TRACE else 81) and not state['done'] and not state['writes'] and (0,0) in state['stages'] and (2,0) in state['stages']
  print('PASS missing ARM7 pause-ready -> visible S0/S2 then bounded S9 timeout, no card writes',flush=True);return state
 if partial:
  assert state['fault']==1 and not state['done'] and state['own']==14 and state['peer']==12
  print('PASS apply read failure holds both CPUs, no normal release',flush=True);return state
 assert state['minsp9']>=stack,'ARM9 worker stack overflow'
 assert state['done'] and state['fault'] is None,{'pc':hex(u.reg_read(UC_ARM_REG_PC)),**{k:v for k,v in state.items() if k not in ('buffer','stages')}}
 assert fifo7==[0x90001234] and fifo9==[0x12345678,0x55aa55aa],(fifo7,fifo9)
 if load and not (corrupt or identity or empty or TRACE):
  assert state['restored'] and state['cpclosed'];assert u.reg_read(UC_ARM_REG_PC)==pc
  assert bytes(u.mem_read(0x02030000,512))==capture[512+0x30000:512+0x30200]
  assert bytes(a7.mem_read(0x03800000,0x10000))==private
  assert bytes(u.mem_read(0x06800000,0xa4000))==targetvideo[:0xa4000]
  assert [u.mem_read(a,1)[0] for a in vc]==list(v[9:18])
  saved=b''.join(disk[a] for a in physical);hh=words(saved[:512])
  current=bytearray(u.mem_read(0x02000000,0x400000));expected=bytearray(saved[512:512+0x400000])
  for start,size in ((base,meta['memory_bytes']),(hh[37]-56,76)):
   if 0x02000000<=start<0x02400000:expected[start-0x02000000:start-0x02000000+size]=current[start-0x02000000:start-0x02000000+size]
  assert current==expected,'Main RAM differs outside worker and dead handoff frame'
  assert bytes(u.mem_read(h0[10],0x4000))==saved[512+0x400000:512+0x404000]
  assert bytes(u.mem_read(0x01ff8000,0x8000))==saved[512+0x404000:512+0x40c000]
  assert [cp[k] for k in cpkeys]==list(hh[81:100]),'Final CP15 differs from captured CPU state'
  assert [u.reg_read(reg) for reg in REGS]==list(hh[20:33])
  assert u.reg_read(UC_ARM_REG_SP)==hh[33] and u.reg_read(UC_ARM_REG_LR)==hh[34]
  assert u.reg_read(UC_ARM_REG_CPSR)==hh[36]|(32 if hh[34]&1 else 0)
  assert state['minsp9']>=stack,'ARM9 worker stack overflow'
  print('Verified all RAM/TCM bytes, 19 CP15 registers, general registers, SP/LR/CPSR; maximum observed worker stack',stack+1024-state['minsp9'],flush=True)
 elif load:
  assert not state['restored'] and not state['writes'];assert any(stage==8 for stage,_ in state['stages'])
  if TRACE:assert (8,1007) in state['stages']
  if empty:assert (8,1001) in state['stages'] and state['readcount']==1
  assert bytes(u.mem_read(0x02030000,16))==b'changed progress'
 else:
  blob=b''.join(disk[a] for a in physical);h=words(blob[:512]);assert h[4]==2 and h[19]==6
  assert h[6]==zlib.crc32(blob[512:]);crc=bytearray(blob[:512]);struct.pack_into('<I',crc,480,0);assert h[120]==zlib.crc32(crc)
  assert blob[512+0x424400:512+0x4c9400]==targetvideo
  assert state['writes']==sectors+1
  if psg_first:
   audio=words(blob[512+0x4c9400:512+0x4c9600])
   assert audio[84+11]==0x300 and audio[4+11*5+2]==0x10000-777 and audio[100+11]&0x80000000
   print('PASS first-save active PSG11 captured with observed timer and 0300 coverage in completed slot',flush=True)
  if '--bus-check' in sys.argv:
   assert struct.unpack('<H',u.mem_read(0x04000204,2))[0]==h0[39]
   assert state['exmem_writes'] and all(not (value&0x8000 and running) for value,running in state['exmem_writes'])
   assert h[39]==h0[39] and not state['server7'],'Original EXMEM was lost or restored before private ACK'
   print('PASS ARM9 main RAM priority acquired before start and original EXMEM restored after ARM7 private ACK',flush=True)
 return state
disk={physical[0]:bytes(blank)}
privateModel=r.parent/'实机记录'/'P4-local-model.bin'
if '--reuse' in sys.argv:
 b=privateModel.read_bytes();disk={a:b[i*512:(i+1)*512] for i,a in enumerate(physical)}
else:
 print('Executing actual P4 save...',flush=True);a=make(disk,psg_first=TRACE);print('PASS full capture, physical extent writes, payload/header CRC, audio shadow and FIFO replay',flush=True)
 privateModel.write_bytes(b''.join(disk[a] for a in physical))
if TRACE:
 make(disk,True,True)
 make({physical[0]:bytes(blank)},arm7_unready=True)
 make({physical[0]:bytes(blank)},ipc_unlatched=True)
 make(disk,True,True,release_unready=True)
 for case in ('sd_busy','sound_busy','fifo7_error','fifo9_error','sound_unsupported','sound_coverage','sound_range'):
  make({physical[0]:bytes(blank)},refusal=case)
 make(disk,True,True,source_alias=True)
 print('PASS actual worker preflight accepts mirrored main RAM sound source without canonicalizing playback address',flush=True)
 (f/'trace-save-results.json').write_text(json.dumps({'build_fingerprint':meta['p4_build_fingerprint'],'worker_image_sha256':hashlib.sha256(original).hexdigest(),'save':'PASS','load_disabled':'PASS','ready_timeout':'PASS','ipc_readback_failure':'PASS','private_ack_timeout':'PASS','detailed_refusals':'PASS','sound_source_alias':'PASS','cold_psg11_save':'PASS','bus_priority_policy':'PASS' if '--bus-check' in sys.argv else 'not run','physical_hardware':False},indent=2))
 print('PASS trace save, load disabled with no card writes, ready timeout',flush=True);raise SystemExit(0)
print('Executing independent boot / mutated-state P4 restore...',flush=True);b=make(disk,True,True);print('PASS independent runtime instance: validated file -> main/TCM/WRAM/video/audio + ARM9/ARM7 continuation',flush=True)
if '--restore-only' in sys.argv:
 (f/'p4-full-transport-restore.json').write_text(json.dumps({'restore':'PASS','actual_worker_sd_protocol':True,'physical_hardware':False},indent=2));raise SystemExit(0)
print('Executing wrong ROM identity refusal...',flush=True);make(disk,True,True,identity=True);print('PASS wrong identity returns current game without destructive writes',flush=True)
print('Executing payload corruption refusal...',flush=True);make(disk,True,True,corrupt=True);print('PASS corrupt payload returns current game without destructive writes',flush=True)
make({physical[0]:bytes(blank)},early_refusal=True)
make({physical[0]:bytes(blank)},arm7_unready=True)
print('Executing no-checkpoint refusal...',flush=True);make({physical[0]:bytes(blank)},True,True,empty=True);print('PASS no completed slot -> NO SAVE / fresh B, current game preserved',flush=True)
if '--fast-io' in sys.argv:make(disk,True,True,partial=True)
(f/'p4-model-results.json').write_text(json.dumps({'build_fingerprint':meta['p4_build_fingerprint'],'worker_image_sha256':hashlib.sha256(original).hexdigest(),'save':'PASS','cross_boot_mutated_restore':'PASS','wrong_identity':'PASS','payload_corruption':'PASS','pre_start_refusal':'PASS','arm7_ready_timeout':'PASS','missing_slot':'PASS','apply_read_failure':'PASS' if '--fast-io' in sys.argv else 'not run','sd_interface':'sector callback' if '--fast-io' in sys.argv else 'actual worker SD protocol','physical_hardware':False,'internal_3d_restored':False},indent=2))
