"""Private-ROM integration: real recognizer + compiled atomic MMIO observer ABI.
No ROM bytes are embedded in source or test reports. This is not DS hardware.
"""
from pathlib import Path
import ctypes,hashlib,json,os,struct,subprocess,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();roms=[Path(x) for x in sys.argv[2:]];f=r/'build/rts-sdk-sound';f.mkdir(exist_ok=True)
cxx=os.environ.get('CXX','C:/msys64/mingw64/bin/g++.exe' if os.name=='nt' else 'g++')
exe=f/('recognize.exe' if os.name=='nt' else 'recognize')
subprocess.run([cxx,'-std=c++20','-O2','-static','-I'+str(r/'arm9/source/patches/rts'),str(r/'tests/rts_sdk_sound_harness.cpp'),'-o',str(exe)],check=True)
wf=r/'build/rts-worker-p49';meta=json.loads((wf/'RtsM2Image.json').read_text());base=0x023fa000
prefix=os.environ.get('ARM_NONE_EABI_PREFIX','C:/msys64/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-' if os.name=='nt' else '/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
syms={p[2]:int(p[0],16)-meta['link_base']+base for line in subprocess.check_output([prefix+'nm',str(wf/'worker.elf')],text=True).splitlines() if len(p:=line.split())==3}
image=bytearray((wf/'worker.bin').read_bytes())
for off in meta['relocations']:struct.pack_into('<I',image,off,(struct.unpack_from('<I',image,off)[0]+base-meta['link_base'])&0xffffffff)
loader=r/'build/picoLoader9_DSPICO_restore_p49.elf';common=f/'sound-store.bin'
subprocess.run([prefix+'objcopy','--dump-section','patch_rtsSoundStore='+str(common),str(loader)],check=True)
ls={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(loader)],text=True).splitlines() if len(p:=line.split())==3}
code=bytearray(common.read_bytes());commonBase=0x0380c000
struct.pack_into('<I',code,ls['rtsSoundStoreObserve']-ls['__start_patch_rtsSoundStore'],syms['rtsSoundObserveStore']|1)
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
reports=[];cases=0
for rom in roms:
 plan=json.loads(subprocess.check_output([str(exe),str(rom)],text=True));entry={'rom':rom.name,'recognized':plan['recognized']}
 if not plan['recognized']:reports.append(entry);print('UNRECOGNIZED sound:',rom.name,flush=True);continue
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for a,n in ((0x02000000,0x400000),(0x037f0000,0x20000),(0x04000000,0x2000)):u.mem_map(a,n)
 u.mem_write(base,bytes(image));u.mem_write(commonBase,bytes(code));shadow=syms['gRtsSoundShadow']
 io=[];patched=False
 def write(cpu,ac,address,n,value,d):
  if 0x04000400<=address<0x04000500:
   if patched:
    assert cpu.reg_read(UC_ARM_REG_CPSR)&192==192,'Shadow/MMIO store not IRQ/FIQ atomic'
    assert struct.unpack('<I',cpu.mem_read(shadow+8,4))[0]==1,'MMIO store preceded shadow publication'
   io.append((address,n,value))
 u.hook_add(UC_HOOK_MEM_WRITE,write)
 for index,(_,op,pc) in enumerate(plan['sites']):
  stub=0x0380c200+index*28
  desc=struct.pack('<7I',0xe92d0003,0xe28f1008,0xe59f0000,0xe12fff10,commonBase,op,pc+4)
  u.mem_write(stub,desc)
  rn=(op>>16)&15;rd=(op>>12)&15;half=(op&0x0e000000)==0
  imm=(((op>>4)&240)|(op&15)) if half else op&4095
  field=(8,10,12,4,8,8,8)[index];width=2 if half else 4
  for ch in range(16):
   for cpsr in (0x6000001f,0xa00000d2):
    values=[0x12340000+i*0x100 for i in range(13)];address=0x04000400+ch*16+field
    value=65000+ch if field==8 else 4 if field==10 else 16 if field==12 else 0x02010000+ch*256
    values[rn]=address-imm;values[rd]=value
    expected=[]
    for patched in (False,True):
     u.mem_write(pc,struct.pack('<I',0xea000000|(((stub-pc-8)>>2)&0xffffff) if patched else op))
     u.mem_write(shadow,struct.pack('<4I',0x31485341,1,0,0)+b'\0'*496)
     u.mem_write(address,b'\0'*width);u.reg_write(UC_ARM_REG_CPSR,cpsr)
     for reg,val in zip(regs,values):u.reg_write(reg,val)
     u.reg_write(UC_ARM_REG_SP,0x0380f000);u.reg_write(UC_ARM_REG_LR,0x0380a000);io.clear()
     u.emu_start(pc,pc+4,count=10000)
     result=([u.reg_read(reg) for reg in regs],u.reg_read(UC_ARM_REG_CPSR),u.reg_read(UC_ARM_REG_SP),u.reg_read(UC_ARM_REG_LR),list(io),bytes(u.mem_read(address,width)))
     assert u.reg_read(UC_ARM_REG_PC)==pc+4
     if not patched:expected=result
     else:
      assert result==expected,('Changed store ABI',rom.name,index,ch,hex(pc))
      fieldIndex={4:1,8:2,10:3,12:4}[field]
      assert struct.unpack('<I',u.mem_read(shadow+16+ch*20+fieldIndex*4,4))[0]==value
      coverage=struct.unpack('<I',u.mem_read(shadow+336+ch*4,4))[0]
      assert coverage==((1<<width)-1)<<field
      cases+=1
 entry['store_abi_cases']=224;reports.append(entry);print('PASS atomic original-vs-patched stores:',rom.name,flush=True)
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
dll=f/('muted-test.dll' if os.name=='nt' else 'muted-test.so')
subprocess.run([cc,'-shared','-O2','-I'+str(r/'common'),str(r/'runtime/rts/sound-restart.c'),'-o',str(dll)],check=True)
lib=ctypes.CDLL(str(dll));fn=lib.RtsBuildSoundRestartOrMute
fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
shadowWords=(ctypes.c_uint32*128)();controls=(ctypes.c_uint32*16)();planWords=(ctypes.c_uint32*128)()
shadowWords[0]=0x31485341;shadowWords[1]=1;shadowWords[3]=1;controls[0]=0x8800407f
assert fn(shadowWords,controls,0x807f,512,0,planWords)==0
assert list(planWords[:5])==[0x31525341,1,0x807f,512,0]
for mask in (0x80,0x8000,0x8080):
 for i in range(128):planWords[i]=0xa5a5a5a5
 assert fn(shadowWords,controls,0x807f,512,mask,planWords)!=0 and all(x==0xa5a5a5a5 for x in planWords)
print('PASS missing sound metadata -> muted plan; active audio capture writer is separately refused',flush=True)
result={'build_fingerprint':meta['p4_build_fingerprint'],'worker_image_sha256':hashlib.sha256((wf/'worker.bin').read_bytes()).hexdigest(),'atomic_store_abi_cases':cases,'muted_sound_plan':'PASS','active_capture_guard':'PASS','roms':reports,'physical_hardware':False}
(f/'generic-store-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS generic store ABI:',cases,'cases',flush=True)
