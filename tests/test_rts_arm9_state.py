"""Execute bank/CP15 capture and restore, including region-2 handoff ordering.
CP15/cache actions are modeled, not physical cache-coherence validation.
"""
import ctypes as C,importlib.util,json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();private=Path(sys.argv[2]) if len(sys.argv)>2 else None
saved=sys.argv;sys.argv=[str(r/'tests/test_rts_arm9_continuation.py'),str(r)]
spec=importlib.util.spec_from_file_location('continuation',r/'tests/test_rts_arm9_continuation.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);sys.argv=saved
f=r/'build/rts-arm9-state';f.mkdir(exist_ok=True);prefix=a.prefix
ld=f/'state.ld';ld.write_text('SECTIONS { . = 0x023fa000; .capture : { *(.text.rtsCaptureArm9Cpu) } .restore : { *(.text.rtsRestoreArm9State) } . = 0x02000780; .tail : { *(.text.rtsArm9RestoreTail) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } }')
elf=f/'state.elf';subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-nostdlib','-Wl,--build-id=none,-e,rtsCaptureArm9Cpu','-T',str(ld),str(r/'runtime/rts/arm9-cpu-capture.s'),str(r/'runtime/rts/arm9-state-restore.s'),'-o',str(elf)],check=True)
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=line.split())==3}
raw=elf.read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
cpkeys=[(1,0,0),(2,0,0),(2,0,1),(3,0,0),(5,0,2),(5,0,3)]+[(6,i,0) for i in range(8)]+[(9,1,0),(9,1,1),(9,0,0),(9,0,1),(13,0,1)]
class CpuState(C.Structure):_fields_=[('words',C.c_uint32*128)]
def run(blob,label,bad_context=False):
 h=a.hwords(blob);result,continuation,_=a.prepare(blob);assert result==0
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for addr,n in [(0x02000000,0x400000),(h[10],0x4000),(0x01ff8000,0x8000)]:u.mem_map(addr,n)
 u.mem_write(0x02000000,bytes(blob[512:512+0x400000]));u.mem_write(h[10],bytes(blob[512+0x400000:512+0x404000]));u.mem_write(0x01ff8000,bytes(blob[512+0x404000:512+0x40c000]))
 for i in range(phnum):
  kind,off,addr,pa,filesz,memsz,flags,align=struct.unpack_from('<8I',raw,phoff+i*phsize)
  if kind==1 and filesz:u.mem_write(addr,raw[off:off+filesz])
 target=[h[14],0x42,h[40] or 0x42,h[41] or 2,0x15111011,0x55111111,
         0x04000033,0x0200002b,h[38],0x08000035,0x027c001b,0x0100002f,0xffff001d,0x027ff017,h[15] or 0x027c000a,h[16] or 0x20,0,0,0x1234]
 cp=dict(zip(cpkeys,target));cp[(6,2,0)]=0 # Capture sees the temporary guard opening.
 state={'mode':'capture','ops':[],'returned':False,'closed':False};ctx=0x023fc000;stop=0x020f0000
 u.mem_write(ctx,b'\0'*512);u.mem_write(stop,b'\x1e\xff\x2f\xe1')
 banks=[];modes=(31,18,19,23,27,17)
 for i,mode in enumerate(modes):
  u.reg_write(UC_ARM_REG_CPSR,0xc0|mode);sp=h[10]+0x3000+i*64;lr=0x12340000+i*4;spsr=0 if mode==31 else 0xa000001f+i*0x1000000
  u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,lr)
  if mode!=31:u.reg_write(UC_ARM_REG_SPSR,spsr)
  banks.append([sp,lr,spsr])
 fiq=[0xf1f00000+i for i in range(5)]
 for reg,v in zip(a.REGS[8:],fiq):u.reg_write(reg,v)
 u.reg_write(UC_ARM_REG_CPSR,0x600000df);u.reg_write(UC_ARM_REG_SP,0x023fd000);u.reg_write(UC_ARM_REG_LR,stop)
 general=[0x11110000+i for i in range(13)]
 for reg,v in zip(a.REGS,general):u.reg_write(reg,v)
 for reg,v in zip(a.REGS,[ctx,h[33],h[34],h[38]]):u.reg_write(reg,v)
 def read(uc,ac,addr,n,v,d):
  if state['mode']=='restore' and cp[(6,2,0)]&1 and 0x023e0000<=addr<0x02400000:raise PermissionError('Context read after worker region closed')
 def write(uc,ac,addr,n,v,d):
  if state['mode']=='capture':assert ctx<=addr and addr+n<=ctx+512,'Capture wrote game memory'
  else:raise AssertionError(('Restore wrote memory',hex(addr)))
 def code(uc,addr,n,d):
  if state['mode']=='restore' and cp[(6,2,0)]&1 and 0x023e0000<=addr<0x02400000:raise PermissionError('Worker executed after region closed')
  ins=struct.unpack('<I',uc.mem_read(addr,4))[0]
  if ins&0x0f000f10==0x0e000f10:
   key=((ins>>16)&15,ins&15,(ins>>5)&7);rd=(ins>>12)&15
   if ins&(1<<20):uc.reg_write(a.REGS[rd],cp[key])
   else:
    assert state['mode']=='restore','Capture unexpectedly wrote CP15'
    value=uc.reg_read(a.REGS[rd]);state['ops'].append((key,value,addr))
    if key==(6,2,0) and value&1:
     assert 0x02000000<=addr<0x02000800,'Region 2 closed outside secure tail'
     state['closed']=True
    if key[0]!=7:cp[key]=value
   uc.reg_write(UC_ARM_REG_PC,addr+4);return
  if addr==stop and state['mode']=='capture':state['returned']=True;uc.emu_stop()
  if state['mode']=='restore' and addr==continuation.regs[13]:state['returned']=True;uc.emu_stop()
 u.hook_add(UC_HOOK_CODE,code);u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.emu_start(syms['rtsCaptureArm9Cpu'],0,count=1000)
 assert state['returned'] and u.reg_read(UC_ARM_REG_CPSR)==0x600000df and u.reg_read(UC_ARM_REG_SP)==0x023fd000
 assert [u.reg_read(reg) for reg in a.REGS[4:12]]==general[4:12]
 words=struct.unpack('<128I',u.mem_read(ctx,512));banks[0]=[h[33],h[34],0]
 assert words[:4]==(0x31503941,1,0x600000df,0)
 assert words[4:22]==tuple(v for bank in banks for v in bank)
 assert words[22:27]==tuple(fiq) and words[27:46]==tuple(target) and not any(words[46:])
 # Clobber all inactive banks. Assembly restore runs on main-RAM code only.
 for mode in modes:
  u.reg_write(UC_ARM_REG_CPSR,0xc0|mode);u.reg_write(UC_ARM_REG_SP,0xdead0000+mode*16);u.reg_write(UC_ARM_REG_LR,0xbad00000+mode)
  if mode!=31:u.reg_write(UC_ARM_REG_SPSR,0x10)
  if mode==17:
   for reg in a.REGS[8:]:u.reg_write(reg,0xeeeeeeee)
 for key in cpkeys:cp[key]=0
 cp[(1,0,0)]=target[0]&~4;cp[(6,2,0)]=0
 tailctx=0x023fc400 if bad_context else h[37]-56
 tail=C.string_at(C.byref(continuation),68)+struct.pack('<II',h[38],h[14]);u.mem_write(tailctx,tail)
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,0x023fd000);u.reg_write(UC_ARM_REG_LR,stop)
 for reg,v in zip(a.REGS,[ctx,tailctx,syms['rtsArm9RestoreTail']]):u.reg_write(reg,v)
 state.update(mode='restore',returned=False)
 try:u.emu_start(syms['rtsRestoreArm9State'],0,count=1000)
 except PermissionError:
  assert bad_context;print('PASS rejects former workspace-context handoff after MPU close');return
 assert not bad_context,'Protected context regression escaped'
 assert state['returned'] and state['closed'] and [cp[k] for k in cpkeys]==target
 assert u.reg_read(UC_ARM_REG_CPSR)==continuation.cpsr and u.reg_read(UC_ARM_REG_SP)==h[33] and u.reg_read(UC_ARM_REG_LR)==h[34]
 assert [u.reg_read(reg) for reg in a.REGS]==list(continuation.regs)[:13]
 for i,mode in enumerate(modes):
  u.reg_write(UC_ARM_REG_CPSR,0xc0|mode)
  assert u.reg_read(UC_ARM_REG_SP)==banks[i][0] and u.reg_read(UC_ARM_REG_LR)==banks[i][1]
  if mode!=31:assert u.reg_read(UC_ARM_REG_SPSR)==(continuation.cpsr if mode==18 else banks[i][2])
  if mode==17:assert [u.reg_read(reg) for reg in a.REGS[8:]]==fiq
 print('PASS',label,'captured/restored 19 CP15 registers and six banks; final region-2 closure only in secure tail; no game-memory writes')
run(a.fixture(False),'ARM caller');run(a.fixture(True),'Thumb caller');run(a.fixture(False),'negative context location',True)
if private:run(private.read_bytes(),'M3.2 real continuation + synthetic supplemental CPU state')
(f/'RESULTS.json').write_text(json.dumps({'capture_banked_cp15':'PASS','cold_restore_banks_cp15':'PASS','secure_tail_region2_order':'PASS','protected_context_negative':'PASS','private_continuation':'PASS' if private else 'not supplied','supplemental_cpu_state_is_synthetic':True,'hardware_tested':False,'live_restore_enabled':False},indent=2))
