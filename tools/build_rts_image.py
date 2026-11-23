"""Turn a self-contained ARM ELF into an image with checked ABS32 relocations."""
import json,struct,subprocess,sys
from pathlib import Path
elf,out,prefix=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
symbols={}
for line in subprocess.check_output([prefix+'nm',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)==3:symbols[p[2]]=int(p[0],16)
base,end=symbols['__image_start'],symbols['__image_end']
assert base==0x02200000 and 0<end-base<=0x10000
binary=elf.with_suffix('.bin')
subprocess.run([prefix+'objcopy','-O','binary',str(elf),str(binary)],check=True)
blob=binary.read_bytes()
relocs=[]
for line in subprocess.check_output([prefix+'readelf','-rW',str(elf)],text=True).splitlines():
    p=line.split()
    if len(p)<5 or not p[0].isalnum() or not p[2].startswith('R_ARM_'):continue
    address=int(p[0],16);kind=p[2]
    if kind in ('R_ARM_CALL','R_ARM_JUMP24','R_ARM_THM_CALL','R_ARM_V4BX'):
        if kind!='R_ARM_V4BX':assert base<=int(p[3],16)<end,line
        continue
    assert kind in ('R_ARM_ABS32','R_ARM_TARGET1'),line
    offset=address-base
    assert 0<=offset<=len(blob)-4 and offset%4==0,line
    value=struct.unpack_from('<I',blob,offset)[0]
    assert base<=value<=end,line
    relocs.append(offset)
assert len(relocs)==len(set(relocs))
def array(name,values,typ,width):
    lines=[f'inline constexpr {typ} {name}[] = {{']
    for n in range(0,len(values),16):lines.append('    '+','.join(f'0x{x:0{width}x}' for x in values[n:n+16])+',')
    return '\n'.join(lines+['};'])
text='#pragma once\n#include <stdint.h>\n'
for name,value in [('LINK_BASE',base),('MEMORY_BYTES',end-base),('CONFIG_OFFSET',symbols['gRtsM2']-base),('ENTRY_OFFSET',symbols['rtsM2Entry']-base)]:
    text+=f'inline constexpr uint32_t RTS_M2_{name} = 0x{value:x};\n'
text+=array('RTS_M2_IMAGE',list(blob),'uint8_t',2)+'\n'
text+=array('RTS_M2_RELOCS',relocs,'uint32_t',8)+'\n'
out.write_text(text,encoding='utf-8')
report={'link_base':base,'memory_bytes':end-base,'file_bytes':len(blob),'config_offset':symbols['gRtsM2']-base,'entry_offset':symbols['rtsM2Entry']-base,'relocations':relocs}
out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('M2 runtime:',len(blob),'image bytes,',end-base,'reserved bytes,',len(relocs),'checked relocations')
