import ctypes as C,hashlib,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import *
r=Path(sys.argv[1]).resolve();f=r/'build/rts-identity-test';f.mkdir(exist_ok=True)
gcc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc');prefix=os.environ.get('ARM_NONE_EABI_PREFIX',str(Path(os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful'))/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
subprocess.run([gcc,'-shared','-O2','-I'+str(r/'common'),str(r/'common/RtsSha256.c'),str(r/'common/RtsSavePath.c'),'-o',str(f/'identity.dll')],check=True)
d=C.CDLL(str(f/'identity.dll'));d.RtsSha256Init.argtypes=[C.c_void_p];d.RtsSha256Update.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];d.RtsSha256Finish.argtypes=[C.c_void_p,C.c_void_p]
def native(data,step):
 c=C.create_string_buffer(112);out=C.create_string_buffer(32);d.RtsSha256Init(c)
 for i in range(0,len(data),step):b=data[i:i+step];d.RtsSha256Update(c,b,len(b))
 d.RtsSha256Finish(c,out);return out.raw
for n in (0,1,55,56,63,64,65,127,128,4096,8193):
 b=bytes((i*73+11)&255 for i in range(n))
 for step in (1,7,64,4096):assert native(b,step)==hashlib.sha256(b).digest(),(n,step)
d.RtsMakeSavePath.argtypes=[C.c_char_p,C.c_void_p,C.c_size_t]
for rom,want in [('逆转裁判2.nds','逆转裁判2.rts'),('/点.目录/逆转裁判2.NDS','/点.目录/逆转裁判2.rts'),('/Games/noextension','/Games/noextension.rts'),('C:\\Games\\game.v1.nds','C:\\Games\\game.v1.rts')]:
 out=C.create_string_buffer(1024);assert d.RtsMakeSavePath(rom.encode(),out,1024);assert out.value.decode()==want
 sentinel=C.create_string_buffer(b'unchanged');assert not d.RtsMakeSavePath(rom.encode(),sentinel,3);assert sentinel.value==b'unchanged'
ld=f/'sha.ld';ld.write_text('ENTRY(RtsSha256Init) SECTIONS { . = 0x02010000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } }')
elf=f/'sha.elf';subprocess.run([prefix+'gcc','-mcpu=arm7tdmi','-mthumb','-Os','-ffreestanding','-fno-builtin','-nostdlib','-T',str(ld),str(r/'common/RtsSha256.c'),'-lgcc','-o',str(elf)],check=True)
symbols={p[2]:int(p[0],16) for l in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines() if len(p:=l.split())==3}
subprocess.run([prefix+'objcopy','-O','binary',str(elf),str(f/'sha.bin')],check=True)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x02000000,0x400000);u.mem_write(0x02010000,(f/'sha.bin').read_bytes())
def call(name,args):
 u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_SP,0x023f0000);u.reg_write(UC_ARM_REG_LR,0x02000101)
 for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):u.reg_write(reg,val)
 u.emu_start(symbols[name]|1,0x02000100,count=20000000);assert u.reg_read(UC_ARM_REG_PC)==0x02000100
for n in (0,55,56,64,65,4096):
 b=bytes((i*17)&255 for i in range(n));u.mem_write(0x02040000,b or b'\0');call('RtsSha256Init',[0x02030000]);call('RtsSha256Update',[0x02030000,0x02040000,n]);call('RtsSha256Finish',[0x02030000,0x02030100]);assert bytes(u.mem_read(0x02030100,32))==hashlib.sha256(b).digest()
print('PASS native + actual ARM7 SHA256 padding/streaming; UTF-8 same-name .rts paths; bounded no-write failure')
