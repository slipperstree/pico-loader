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
overlay='gRtsMenuCoreBoot' in symbols
subprocess.run([prefix+'objcopy','-O','binary','--only-section=.text','--only-section=.rodata','--only-section=.data',str(elf),str(binary)],check=True)
menu_base=0x06898000
menu_path=elf.with_name('menu-overlay.bin')
if overlay:subprocess.run([prefix+'objcopy','-O','binary','--only-section=.menu',str(elf),str(menu_path)],check=True)
menu_blob=menu_path.read_bytes() if overlay else b''
assert len(menu_blob)<=32768
menu_relocs=[]
blob=binary.read_bytes()
relocs=[]
debug_relocations=False
for line in subprocess.check_output([prefix+'readelf','-rW',str(elf)],text=True).splitlines():
    if line.startswith('Relocation section '):
        debug_relocations="'.rel.debug" in line or "'.rela.debug" in line
    if debug_relocations:continue # libgcc debug records are not loaded/relocated
    p=line.split()
    if len(p)<5 or not p[0].isalnum() or not p[2].startswith('R_ARM_'):continue
    address=int(p[0],16);kind=p[2]
    if overlay and base<=address<end and menu_base<=int(p[3],16)<menu_base+len(menu_blob):
        assert not p[4].startswith(('__aeabi','__div','__udiv')), 'Resident math must not depend on an unloaded overlay: '+line
    if kind in ('R_ARM_CALL','R_ARM_JUMP24','R_ARM_THM_CALL','R_ARM_V4BX'):
        if kind!='R_ARM_V4BX':assert base<=int(p[3],16)<end or (overlay and menu_base<=int(p[3],16)<menu_base+len(menu_blob)),line
        continue
    assert kind in ('R_ARM_ABS32','R_ARM_TARGET1'),line
    in_menu=overlay and menu_base<=address<menu_base+len(menu_blob)
    offset=address-(menu_base if in_menu else base)
    data=menu_blob if in_menu else blob
    assert 0<=offset<=len(data)-4 and offset%4==0,line
    value=struct.unpack_from('<I',data,offset)[0]
    # Thumb address factoring may use a signed addend outside the image.
    # The relocation anchor must be internal; preserve the compiler addend.
    anchor=int(p[3],16)
    assert base<=anchor<=end or (overlay and menu_base<=anchor<menu_base+len(menu_blob)),line
    if base<=anchor<=end:(menu_relocs if in_menu else relocs).append(offset)
# GNU ld's generated interworking veneers have no emitted ABS32 relocation.
# Validate the exact veneer shape before adding its internal pointer literal.
for name,address in symbols.items():
    if not name.startswith('__') or not name.endswith(('_from_arm','_from_thumb','_veneer')):continue
    in_menu=overlay and menu_base<=(address&~1)<menu_base+len(menu_blob)
    data=menu_blob if in_menu else blob;off=(address&~1)-(menu_base if in_menu else base)
    first=struct.unpack_from('<I',data,off)[0];literal=None
    if first==0xe59fc000:
        second,target=struct.unpack_from('<2I',data,off+4);assert second==0xe12fff1c,name;literal=off+8
    elif first==0xe7fd4778:
        second=struct.unpack_from('<I',data,off+4)[0]
        if second>>24==0xea:continue
        if second==0xe51ff004:literal=off+8
        elif second==0xe59fc000:
            assert struct.unpack_from('<I',data,off+8)[0]==0xe12fff1c,name;literal=off+12
        else:raise AssertionError((name,hex(first),hex(second)))
    elif first==0xe51ff004:literal=off+4
    elif first==0x47184b00:literal=off+4
    else:raise AssertionError((name,hex(first)))
    target=struct.unpack_from('<I',data,literal)[0]&~1
    assert base<=target<end or (overlay and menu_base<=target<menu_base+len(menu_blob)),(name,hex(target))
    if base<=target<end:
        dest=menu_relocs if in_menu else relocs
        if literal not in dest:dest.append(literal)
menu_relocs.sort()
assert len(menu_relocs)==len(set(menu_relocs)) and len(menu_relocs)<=1024
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
    assert end-base<=0x5000, 'RTS exceeds reserved workspace limit'
    fingerprint=hashlib.sha256(blob+menu_blob+struct.pack('<I',end-base))
    for name in ('arm9/source/patches/rts/RtsSdkSound.h','arm9/source/patches/rts/RtsProbe.cpp','arm9/source/patches/rts/RtsProbe7.s','arm9/source/patches/rts/RtsProbe9.s','arm9/source/patches/rts/RtsSoundHooks7.s','common/RtsP4.h','common/RtsP4Profile.h','common/RtsSnapshotInfo.h','common/RtsSavePath.c','common/RtsSha256.c','arm7/source/loader/NdsLoader.cpp','arm7/source/loader/RtsSnapshotPrepare.cpp'):
        fingerprint.update(Path(name).read_bytes())
    text+=f'inline constexpr uint32_t RTS_P4_POINTERS_OFFSET = 0x{symbols["gRtsP4Pointers"]-base:x};\n'
    text+=f'inline constexpr uint32_t RTS_P4_TAIL_BYTES = 0x{symbols["rtsArm9RestoreTailEnd"]-symbols["rtsArm9RestoreTail"]:x};\n'
    text+=array('RTS_P4_BUILD_SHA256',list(fingerprint.digest()),'uint8_t',2)+'\n'
if overlay:text+=f'inline constexpr uint32_t RTS_MENU_BOOT_OFFSET = 0x{symbols["gRtsMenuCoreBoot"]-base:x};\n'
text+=array('RTS_M2_IMAGE',list(blob),'uint8_t',2)+'\n'
text+=array('RTS_M2_RELOCS',relocs,'uint32_t',8)+'\n'
if overlay:
    overlay_header='#pragma once\n#include <stdint.h>\n'
    overlay_header+=array('RTS_MENU_OVERLAY_IMAGE',list(menu_blob),'uint8_t',2)+'\n'
    overlay_header+=array('RTS_MENU_OVERLAY_RELOCS',menu_relocs,'uint32_t',8)+'\n'
    out.with_name('RtsMenuOverlay.h').write_text(overlay_header,encoding='utf-8')
out.write_text(text,encoding='utf-8')
report={'link_base':base,'memory_bytes':end-base,'file_bytes':len(blob),'config_offset':symbols['gRtsM2']-base,'clock_offset':symbols['gRtsM2Frames']-base,'entry_offset':symbols['rtsM2Entry']-base,'relocations':relocs}
for symbol,label in [('gRtsArm7Mailbox','mailbox'),('rtsArm7CaptureContext','arm7_capture'),('rtsArm7CaptureService','arm7_service')]:
    if symbol in symbols:report[label+'_offset']=symbols[symbol]-base
if 'gRtsP4Pointers' in symbols:
    report['p4_pointers_offset']=symbols['gRtsP4Pointers']-base
    report['arm7_stack_bytes']=384
    report['p4_tail_bytes']=symbols['rtsArm9RestoreTailEnd']-symbols['rtsArm9RestoreTail']
    report['p4_build_fingerprint']=fingerprint.hexdigest()
if overlay:report['menu_overlay_bytes']=len(menu_blob);report['menu_relocations']=menu_relocs
out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('M2 runtime:',len(blob),'image bytes,',end-base,'reserved bytes,',len(relocs),'checked relocations')
