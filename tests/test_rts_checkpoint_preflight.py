"""Execute full-file integrity/identity inspection natively and on ARM946.
Fixtures are generated synthetic data; no private ROM/snapshot is embedded.
"""
import ctypes as C,hashlib,json,os,struct,subprocess,sys,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();f=r/'build/rts-preflight';f.mkdir(exist_ok=True)
tc=Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful'));prefix=str(tc/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
if os.name=='nt':os.environ['PATH']=str(tc/'bin')+os.pathsep+str(Path(prefix).parent)+os.pathsep+os.environ['PATH']
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc');lib=f/('preflight.dll' if os.name=='nt' else 'preflight.so')
subprocess.run([cc,'-shared','-O2','-Wall','-Wextra','-I'+str(r/'common'),str(r/'runtime/rts/checkpoint-preflight.c'),'-o',str(lib)],check=True)
subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-nostdlib','-Wl,--build-id=none,-Ttext=0x02200000,-e,RtsInspectCheckpoint','-I'+str(r/'common'),str(r/'runtime/rts/checkpoint-preflight.c'),'-o',str(f/'preflight.elf')],check=True)
subprocess.run([prefix+'objcopy','-O','binary',str(f/'preflight.elf'),str(f/'preflight.bin')],check=True)
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(f/'preflight.elf')],text=True).splitlines() if len(p:=line.split())==3}
Reader=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_void_p)
native=C.CDLL(str(lib));inspect=native.RtsInspectCheckpoint
inspect.argtypes=[Reader,C.c_void_p,C.c_uint32,C.c_void_p,C.c_void_p];inspect.restype=C.c_int
expected=struct.pack('<II',0x4a473241,0x03017532)+hashlib.sha256(b'exact ROM fixture').digest()+hashlib.sha256(b'exact build fixture').digest()+bytes(range(1,17))
def header_crc(b):
 struct.pack_into('<I',b,116,0);struct.pack_into('<I',b,116,zlib.crc32(b[:512]))
def fixture(full):
 sizes=[(1,0x400000,0x02000000),(2,0x4000,0x027c0000),(3,0x8000,0x01ff8000),(4,0x10000,0x03800000),(5,0x8000,0x03000000),(6,0xa4000,0x06800000),(7,2048,0x05000000),(8,2048,0x07000000)]+[(k,512,0) for k in range(9,16)]
 if not full:sizes=[(9,512,0),(11,512,0)]
 b=bytearray(512);struct.pack_into('<8I',b,0,0x34435452,0x40001,512,0,0x4a473241,0x03017532,31,2);b[32:112]=expected[8:]
 struct.pack_into('<I',b,112,len(sizes));struct.pack_into('<I',b,124,1)
 for i,(kind,n,base) in enumerate(sizes):
  data=bytes((j*13+kind)%256 for j in range(256))*(n//256)
  struct.pack_into('<6I',b,128+i*24,kind,len(b),n,zlib.crc32(data),base,0);b+=data
 struct.pack_into('<I',b,12,len(b));struct.pack_into('<I',b,120,zlib.crc32(b[512:]));header_crc(b);return b
def run(blob,expectedResult=0,failSector=None,identity=expected,actualBytes=None):
 out=C.create_string_buffer(bytes([0xa5])*528);calls=[]
 @Reader
 def read(user,index,dst):
  calls.append(index)
  assert C.string_at(out,528)==bytes([0xa5])*528,'Partial output visible during read'
  if index==failSector:return 0
  if index>=len(blob)//512:return 0
  C.memmove(dst,bytes(blob[index*512:(index+1)*512]),512);return 1
 result=inspect(read,None,len(blob) if actualBytes is None else actualBytes,C.create_string_buffer(identity),out)
 assert result==expectedResult,(result,expectedResult)
 if result:assert C.string_at(out,528)==bytes([0xa5])*528
 else:
  assert struct.unpack_from('<4I',out)[:3]==(1,1,0),'Diagnostic manifest authorized restore'
  assert C.string_at(C.addressof(out)+16,512)==blob[:512]
  assert calls==list(range(len(blob)//512))
 return len(calls)
big=fixture(True);run(big);assert run(big,2,failSector=len(big)//512-1)==len(big)//512
for offset in (32,64,96):
 b=bytearray(big);b[offset]^=1;header_crc(b);assert run(b,5)==1
for offset in (0,4,8,16,20,24,28,112,124):
 b=bytearray(big);b[offset]^=1;header_crc(b)
 # game/SDK are identity; supported capability changes alone are descriptive.
 if offset in (16,20):run(b,5)
 elif offset==24:run(b)
 else:run(b,3 if offset in (0,4,8,28,124) else 6)
b=bytearray(big);b[116]^=1;run(b,4)
for offset in (128,132,136,144,148,128+24):
 b=bytearray(big);b[offset]^=1;header_crc(b);run(b,6)
b=bytearray(big);b[-1]^=1;run(b,7)
struct.pack_into('<I',b,128+14*24+12,zlib.crc32(b[-512:]));header_crc(b);run(b,8)
run(big,3,actualBytes=len(big)-512)
zero=bytearray(expected);zero[8:40]=b'\0'*32;run(big,1,identity=bytes(zero))
print('PASS native full fixture, entire-file reads, ROM/build/session mismatch, truncation, forged layouts, per-section/global CRC and no partial publication')
# Actual ARM binary invokes a modeled sector reader. Output remains untouched
# until the final input sector has been consumed. No game-memory write API.
small=fixture(False)
for failSector in (None,2):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x02000000,0x400000);u.mem_write(0x02200000,(f/'preflight.bin').read_bytes())
 exp,out,sp=0x023f1000,0x023f2000,0x023f0000;readfn,done=0x02010000,0x02020000
 u.mem_write(exp,expected);u.mem_write(out,b'\xa5'*528);u.mem_write(readfn,b'\x1e\xff\x2f\xe1');u.mem_write(done,b'\x1e\xff\x2f\xe1');u.mem_write(sp,struct.pack('<I',out));calls=[]
 def code(uc,addr,n,d):
  if addr==readfn:
   index=uc.reg_read(UC_ARM_REG_R1);dst=uc.reg_read(UC_ARM_REG_R2);calls.append(index)
   assert bytes(uc.mem_read(out,528))==b'\xa5'*528
   assert 0x023e0000<=dst<=0x023ff000-512
   if index==failSector:uc.reg_write(UC_ARM_REG_R0,0)
   else:uc.mem_write(dst,bytes(small[index*512:(index+1)*512]));uc.reg_write(UC_ARM_REG_R0,1)
   uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 def write(uc,ac,addr,n,v,d):assert 0x023e0000<=addr and addr+n<=0x023ff000,'Preflight modified game memory'
 u.hook_add(UC_HOOK_CODE,code);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,done)
 for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(readfn,0,len(small),exp)):u.reg_write(reg,v)
 u.emu_start(syms['RtsInspectCheckpoint'],done,count=1000000)
 assert u.reg_read(UC_ARM_REG_PC)==done and u.reg_read(UC_ARM_REG_R0)==(0 if failSector is None else 2)
 result=bytes(u.mem_read(out,528));assert result==b'\xa5'*528 if failSector else struct.unpack_from('<III',result)==(1,1,0)
 print('PASS ARM946 full-read inspection:', 'success remains diagnostic' if failSector is None else 'last-sector I/O failure leaves output untouched')
(f/'RESULTS.json').write_text(json.dumps({'native_full_manifest_and_identity':'PASS','all_sections_crc_and_bounds':'PASS','no_partial_output_on_error':'PASS','arm946_execution_and_reader':'PASS','diagnostic_cannot_authorize_load':'PASS','writer_loader_integration':False},indent=2))
