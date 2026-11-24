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
    # Thumb address factoring may use a signed addend outside the image.
    # The relocation anchor must be internal; preserve the compiler addend.
    assert base<=int(p[3],16)<=end,line
    relocs.append(offset)
# GNU ld's generated interworking veneers have no emitted ABS32 relocation.
# Validate the exact veneer shape before adding its internal pointer literal.
for name,address in symbols.items():
    if not name.startswith('__') or not name.endswith(('_from_arm','_from_thumb')):continue
    off=(address&~1)-base
    if name.endswith('_from_arm'):
        first,second,target=struct.unpack_from('<3I',blob,off)
        assert (first,second)==(0xe59fc000,0xe12fff1c) and base<=(target&~1)<end,(name,hex(target))
        if off+8 not in relocs:relocs.append(off+8)
    else:
        switch,branch=struct.unpack_from('<2I',blob,off)
        assert switch==0xe7fd4778 and branch>>24==0xea,name
relocs.sort()
assert len(relocs)==len(set(relocs))
def array(name,values,typ,width):
    lines=[f'inline constexpr {typ} {name}[] = {{']
    for n in range(0,len(values),16):lines.append('    '+','.join(f'0x{x:0{width}x}' for x in values[n:n+16])+',')
    return '\n'.join(lines+['};'])
text='#pragma once\n#include <stdint.h>\n'
for name,value in [('LINK_BASE',base),('MEMORY_BYTES',end-base),('CONFIG_OFFSET',symbols['gRtsM2']-base),('CLOCK_OFFSET',symbols['gRtsM2Frames']-base),('ENTRY_OFFSET',symbols['rtsM2Entry']-base)]:
    text+=f'inline constexpr uint32_t RTS_M2_{name} = 0x{value:x};\n'
for symbol,label in [('gRtsArm7Mailbox','MAILBOX'),('rtsArm7CaptureContext','ARM7_CAPTURE'),('rtsArm7CaptureService','ARM7_SERVICE')]:
    if symbol in symbols:text+=f'inline constexpr uint32_t RTS_M3_{label}_OFFSET = 0x{symbols[symbol]-base:x};\n'
if 'gRtsP4Pointers' in symbols:
    import hashlib
    assert end-base<=0x5000, 'P4 exceeds the first-target reserved workspace'
    fingerprint=hashlib.sha256(blob+struct.pack('<I',end-base))
    for name in ('arm9/source/patches/rts/RtsSdkSound.h','arm9/source/patches/rts/RtsProbe.cpp','arm9/source/patches/rts/RtsProbe7.s','arm9/source/patches/rts/RtsProbe9.s','arm9/source/patches/rts/RtsSoundHooks7.s','common/RtsP4.h','common/RtsP4Profile.h','common/RtsSnapshotInfo.h','common/RtsSavePath.c','common/RtsSha256.c','arm7/source/loader/NdsLoader.cpp','arm7/source/loader/RtsSnapshotPrepare.cpp'):
        fingerprint.update(Path(name).read_bytes())
    text+=f'inline constexpr uint32_t RTS_P4_POINTERS_OFFSET = 0x{symbols["gRtsP4Pointers"]-base:x};\n'
    text+=f'inline constexpr uint32_t RTS_P4_TAIL_BYTES = 0x{symbols["rtsArm9RestoreTailEnd"]-symbols["rtsArm9RestoreTail"]:x};\n'
    text+=array('RTS_P4_BUILD_SHA256',list(fingerprint.digest()),'uint8_t',2)+'\n'
text+=array('RTS_M2_IMAGE',list(blob),'uint8_t',2)+'\n'
text+=array('RTS_M2_RELOCS',relocs,'uint32_t',8)+'\n'
out.write_text(text,encoding='utf-8')
report={'link_base':base,'memory_bytes':end-base,'file_bytes':len(blob),'config_offset':symbols['gRtsM2']-base,'clock_offset':symbols['gRtsM2Frames']-base,'entry_offset':symbols['rtsM2Entry']-base,'relocations':relocs}
for symbol,label in [('gRtsArm7Mailbox','mailbox'),('rtsArm7CaptureContext','arm7_capture'),('rtsArm7CaptureService','arm7_service')]:
    if symbol in symbols:report[label+'_offset']=symbols[symbol]-base
if 'gRtsP4Pointers' in symbols:
    report['p4_pointers_offset']=symbols['gRtsP4Pointers']-base
    report['arm7_stack_bytes']=384
    report['p4_tail_bytes']=symbols['rtsArm9RestoreTailEnd']-symbols['rtsArm9RestoreTail']
    report['p4_build_fingerprint']=fingerprint.hexdigest()
out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('M2 runtime:',len(blob),'image bytes,',end-base,'reserved bytes,',len(relocs),'checked relocations')
