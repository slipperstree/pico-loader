"""Validate and execute the unlinked ARM9 continuation primitive.
Optional snapshot argument is user-local data and is never written into source.
This does not emulate an entire NDS restore.
"""
import ctypes as C,json,os,struct,subprocess,sys,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
work=root/'build/rts-continuation-test';work.mkdir(exist_ok=True)
toolchain=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
if os.name=='nt':os.environ['PATH']=str(Path(toolchain)/'bin')+os.pathsep+str(Path(prefix).parent)+os.pathsep+os.environ.get('PATH','')
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
lib=work/('validator.dll' if os.name=='nt' else 'validator.so')
subprocess.run([cc,'-shared','-O2','-ffreestanding','-fno-builtin','-Wall','-Wextra','-I'+str(root/'common'),str(root/'runtime/rts/arm9-continuation.c'),'-o',str(lib)],check=True)
subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-Os','-ffreestanding','-fno-builtin','-Wall','-Wextra','-I'+str(root/'common'),'-c',str(root/'runtime/rts/arm9-continuation.c'),'-o',str(work/'validator.arm.o')],check=True)
elf=work/'return.elf';binary=work/'return.bin';codebase=0x02200000
subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-nostdlib','-Wl,--build-id=none,-Ttext=0x02200000,-e,rtsEnterArm9Continuation',str(root/'runtime/rts/arm9-continuation.s'),'-o',str(elf)],check=True)
subprocess.run([prefix+'objcopy','-O','binary',str(elf),str(binary)],check=True)
class Continuation(C.Structure):_fields_=[('cpsr',C.c_uint32),('sp',C.c_uint32),('lr',C.c_uint32),('regs',C.c_uint32*14)]
Reader=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32)
native=C.CDLL(str(lib));build=native.RtsBuildArm9Continuation
build.argtypes=[C.c_void_p,C.c_int,Reader,C.c_void_p,C.POINTER(Continuation)];build.restype=C.c_int
def hwords(blob):return list(struct.unpack_from('<128I',blob))
def file_offset(h,address,size):
    for base,length,offset in [(0x02000000,0x400000,512),(h[10],0x4000,512+0x400000),(0x01ff8000,0x8000,512+0x404000)]:
        if base<=address and address+size<=base+length:return offset+address-base
    raise ValueError('Uncaptured address')
def prepare(blob,override=None,verified=True,deny_read=False):
    h=hwords(blob) if override is None else list(override);header=(C.c_uint32*128)(*h);out=Continuation()
    C.memset(C.byref(out),0xa5,C.sizeof(out));reads=[]
    @Reader
    def reader(user,address,dst,size):
        reads.append((address,size))
        if deny_read:return 0
        try:offset=file_offset(h,address,size)
        except ValueError:return 0
        C.memmove(dst,bytes(blob[offset:offset+size]),size);return 1
    result=build(header,int(verified),reader,None,C.byref(out))
    if result:assert C.string_at(C.byref(out),68)==bytes([0xa5])*68,'Partially published context'
    return result,out,reads
def fixture(thumb):
    b=bytearray(0x40c200);h=[0]*128
    h[:6]=[0x324d5452,0x20001,len(b),0x4a473241,2,0x40c000]
    h[8:14]=[0x023fa000,0x2200,0x027c0000,0x4000,0x01ff8000,0x8000]
    h[19]=3;h[20:33]=[0x11110000+i for i in range(13)]
    gate=0x0200064c;stub=0x02000700 if thumb else 0x020002a0
    h[33]=0x020a6f30;h[34]=stub+7 if thumb else stub+12;h[35]=0x020001c8;h[36]=0xa000001f;h[37]=h[33]-48;h[38]=0x023e0021
    if thumb:h[23]=gate
    else:h[32]=gate
    def put(addr,data):off=file_offset(h,addr,len(data));b[off:off+len(data)]=data
    frame=[0x4003,0x8002,0x400b,0xdf,h[36],h[23],*h[20:24],h[32],h[34]]
    entry=[0x99990000+i for i in range(14)];entry[4:12]=h[24:32];entry[12:14]=[h[38],h[35]]
    put(h[37],struct.pack('<12I',*frame));put(h[37]-56,struct.pack('<14I',*entry))
    outer=[0x55550000+i for i in range(6)];outer[4 if thumb else 5]=0x02010001 if thumb else 0x02010000
    put(h[33],struct.pack('<'+('5' if thumb else '6')+'I',*outer[:5 if thumb else 6]))
    put(gate,struct.pack('<I',0xe92d500f))
    if thumb:put(stub,struct.pack('<6HI',0xb50f,0x4b02,0x4798,0xbc0f,0xdf06,0xbd00,gate))
    else:
        original=0x02006bac
        put(stub,struct.pack('<8I',0xe92d500f,0xe59fc00c,0xe12fff3c,0xe8bd500f,0xee070f90,0xe59ff000,gate,original+4))
        put(original,struct.pack('<I',0xea000000|(((stub-original-8)>>2)&0xffffff)))
    h[6]=zlib.crc32(b[512:]);struct.pack_into('<128I',b,0,*h)
    return b
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
def execute(blob,label):
    h=hwords(blob);assert zlib.crc32(blob[512:])==h[6]
    result,ctx,_=prepare(blob);assert result==0,(label,result)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for base,size in [(0x02000000,0x400000),(h[10],0x4000),(0x01ff8000,0x8000)]:u.mem_map(base,size)
    u.mem_write(0x02000000,bytes(blob[512:512+0x400000]));u.mem_write(h[10],bytes(blob[512+0x400000:512+0x404000]));u.mem_write(0x01ff8000,bytes(blob[512+0x404000:512+0x40c000]))
    u.mem_write(codebase,binary.read_bytes());ctxaddr=h[8]+0x100;u.mem_write(ctxaddr,C.string_at(C.byref(ctx),68))
    thumb=bool(h[34]&1);post=h[34]&~1
    if thumb:
        caller=struct.unpack('<5I',blob[file_offset(h,h[33],20):file_offset(h,h[33],20)+20]);end=caller[4]&~1
    else:
        caller=struct.unpack('<6I',blob[file_offset(h,h[33],24):file_offset(h,h[33],24)+24]);end=struct.unpack('<I',blob[file_offset(h,post+16,4):file_offset(h,post+16,4)+4])[0]
    u.reg_write(UC_ARM_REG_CPSR,0xd2);u.reg_write(UC_ARM_REG_SP,0x027c3000);u.reg_write(UC_ARM_REG_LR,0x12340000);u.reg_write(UC_ARM_REG_SPSR,0x6000001f)
    u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,h[8]+0x1800);u.reg_write(UC_ARM_REG_LR,0xabcdef00)
    for reg in REGS:u.reg_write(reg,0xeeeeeeee)
    u.reg_write(UC_ARM_REG_R0,ctxaddr);state={'entry':False,'done':False}
    def write(uc,access,addr,size,value,user):raise AssertionError(('Return primitive wrote guest memory',hex(addr)))
    def code(uc,addr,size,user):
        if addr==post:
            state['entry']=True;assert [uc.reg_read(r) for r in REGS]==list(ctx.regs)[:13]
            assert uc.reg_read(UC_ARM_REG_SP)==h[33]
        if addr==post+(2 if thumb else 4):uc.reg_write(UC_ARM_REG_PC,(addr+2)|1 if thumb else addr+4) # Model BIOS wait/WFI completion.
        if addr==end:state['done']=True;uc.emu_stop()
    u.hook_add(UC_HOOK_CODE,code);u.hook_add(UC_HOOK_MEM_WRITE,write)
    u.emu_start(codebase,0,count=1000)
    assert state=={'entry':True,'done':True},(label,state,hex(u.reg_read(UC_ARM_REG_PC)))
    expected=list(h[20:33]);expected[:4]=caller[:4]
    if not thumb:expected[12]=caller[4]
    assert [u.reg_read(r) for r in REGS]==expected
    assert u.reg_read(UC_ARM_REG_SP)==h[33]+(20 if thumb else 24)
    assert u.reg_read(UC_ARM_REG_LR)==(h[34] if thumb else caller[5])
    assert u.reg_read(UC_ARM_REG_CPSR)==h[36]|(0x20 if thumb else 0)
    u.reg_write(UC_ARM_REG_CPSR,0xd2)
    assert u.reg_read(UC_ARM_REG_SP)==0x027c3000 and u.reg_read(UC_ARM_REG_LR)==0x12340000
    print('PASS',label,'validated and resumed caller stub; registers/CPSR/stacks correct, no guest writes')

arm=fixture(False);thumb=fixture(True)
execute(arm,'synthetic ARM WFI');execute(thumb,'synthetic Thumb BIOS wait')
bad=hwords(arm)
for key,value,expected in [(4,1,2),(36,0x92,3),(37,0xffffffe0,4),(34,0x023fa100,5),(24,0xdeadbeef,5)]:
    changed=list(bad);changed[key]=value
    r,_,_=prepare(arm,changed);assert r==expected,(key,r,expected)
r,_,reads=prepare(arm,verified=False);assert r==1 and not reads
r,_,_=prepare(arm,deny_read=True);assert r==7
damaged=bytearray(arm);off=file_offset(bad,0x02006bac,4);struct.pack_into('<I',damaged,off,0xe1a00000)
struct.pack_into('<I',damaged,6*4,zlib.crc32(damaged[512:]))
r,_,_=prepare(damaged);assert r==6
forged=bytearray(arm);struct.pack_into('<I',forged,34*4,0x023fa100)
struct.pack_into('<I',forged,file_offset(bad,bad[37]+11*4,4),0x023fa100)
struct.pack_into('<I',forged,6*4,zlib.crc32(forged[512:]))
r,_,_=prepare(forged);assert r==6
print('PASS incomplete/unverified captures, bad mode/frame/registers/stub/reader rejected without publishing context')
if len(sys.argv)>2:execute(Path(sys.argv[2]).read_bytes(),'user-local diagnostic capture')
(work/'RESULTS.json').write_text(json.dumps({'synthetic_arm':'PASS','synthetic_thumb':'PASS','negative_guards':'PASS','real_capture':'PASS' if len(sys.argv)>2 else 'not supplied','live_restore_enabled':False},indent=2),encoding='utf-8')
