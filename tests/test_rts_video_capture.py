"""Execute actual ARM946 display capture; enforce LCDC mappings and no VRAM writes."""
import json,os,struct,subprocess,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
f=r/'build/rts-worker-m32';meta=json.loads((f/'RtsM2Image.json').read_text());base=meta['link_base']
prefix=os.environ.get('ARM_NONE_EABI_PREFIX','C:/msys64/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-')
syms={p[2]:int(p[0],16) for line in subprocess.check_output([prefix+'nm',str(f/'worker.elf')],text=True).splitlines() if len(p:=line.split())==3}
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for a,n in [(base,0x10000),(0x04000000,0x2000),(0x06800000,0xa4000),(0x05000000,0x1000),(0x07000000,0x1000)]:u.mem_map(a,n)
u.mem_write(base,(f/'worker.bin').read_bytes())
original=bytes((i*31+i//512)%256 for i in range(0xa4000));u.mem_write(0x06800000,original)
palette=bytes((i*7+99)%256 for i in range(2048));oam=bytes((i*3+63)%256 for i in range(2048))
u.mem_write(0x05000000,palette);u.mem_write(0x07000000,oam)
addrs=[0x04000240,0x04000241,0x04000242,0x04000243,0x04000244,0x04000245,0x04000246,0x04000248,0x04000249]
controls=[0x81,0x8a,0x84,0x94,0x83,0x85,0x8d,0x82,0x83]
starts=[0,0x20000,0x40000,0x60000,0x80000,0x90000,0x94000,0x98000,0xa0000,0xa4000]
for a,v in zip(addrs,controls):u.mem_write(a,bytes([v]))
u.mem_write(0x04000247,b'\x03');u.mem_write(0x04000000,struct.pack('<I',0x00110800));u.mem_write(0x04001000,struct.pack('<I',0x00010200))
u.mem_write(0x04000304,struct.pack('<H',0x820f))
ctx=syms['gRtsVideo'];out=base+0xd000;backup=base+0xc000;done=base+0xff00
u.mem_write(done,b'\x1e\xff\x2f\xe1');state={'writes':[],'banks':set()}
def read(uc,ac,a,n,v,d):
 if 0x06800000<=a<0x068a4000:
  bank=next(i for i in range(9) if starts[i]<=a-0x06800000<starts[i+1])
  assert uc.mem_read(addrs[bank],1)[0]==0x80,('Unmapped physical VRAM read',hex(a),bank)
  state['banks'].add(bank)
def write(uc,ac,a,n,v,d):
 assert not (0x06800000<=a<0x068a4000 or 0x05000000<=a<0x05001000 or 0x07000000<=a<0x07001000),'Game graphics memory modified'
 if 0x04000000<=a<0x04002000:
  assert a in addrs and n==1,'Unexpected MMIO write'
  state['writes'].append((a,v))
u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
def call(name,args):
 u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,base+0xf000);u.reg_write(UC_ARM_REG_LR,done)
 for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,v)
 u.emu_start(syms[name],done,count=10000)
 assert u.reg_read(UC_ARM_REG_PC)==done
 return u.reg_read(UC_ARM_REG_R0)
assert call('RtsPrepareVideoCapture',[ctx,0x4003,0x8002])==1 and not state['writes']
h=struct.unpack('<128I',u.mem_read(ctx,512));assert h[:9]==(0x31434456,1,0xa4000,2048,2048,0x00110800,0x00010200,0x4003,0x8002)
assert h[9:18]==tuple(controls) and h[18:20]==(0x820f,3)
row_backup=b''.join(original[0x40000+y*512:0x40000+y*512+192] for y in range(8));u.mem_write(backup,row_backup)
# Model progressOpen after metadata, before display-sector capture.
u.mem_write(0x04000242,b'\x80');live=controls[:];live[2]=0x80
for y in range(8):u.mem_write(0x06840000+y*512,b'\xff\xff'*96)
live_vram=bytes(u.mem_read(0x06800000,0xa4000));captured=bytearray()
for sector in range(1320):
 assert call('RtsReadVideoSector',[ctx,sector,out,backup])==1
 captured+=u.mem_read(out,512)
 assert [u.mem_read(a,1)[0] for a in addrs]==live,'Mapping not restored before return'
assert captured==original+palette+oam,'Original pixels lost or progress overlay leaked'
assert state['banks']==set(range(9)) and len(state['writes'])==1312*2
assert bytes(u.mem_read(0x06800000,0xa4000))==live_vram
before=len(state['writes']);assert call('RtsReadVideoSector',[ctx,1320,out,backup])==0 and len(state['writes'])==before
for bank in (2,3):
 u.mem_write(addrs[bank],b'\x82');assert call('RtsPrepareVideoCapture',[ctx,0,0])==0
 assert len(state['writes'])==before
 u.mem_write(addrs[bank],bytes([live[bank]]))
print('PASS all 1320 display sectors; physical LCDC mapping enforced; exact original VRAM/palette/OAM; progress overlay excluded; live mappings/bytes unchanged; C/D and bounds guards')
(f/'video-test-results.json').write_text(json.dumps({'all_1320_sectors':'PASS','lcdc_mapping_before_read':'PASS','mapping_restored_before_return':'PASS','progress_overlay_excluded':'PASS','no_game_graphics_writes':'PASS','arm7_vram_and_bounds_guards':'PASS','hardware_tested':False},indent=2))
