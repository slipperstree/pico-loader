"""Build real FatFs and the real preparer against an isolated FAT32 file image."""
import os,shutil,struct,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
M32='--m32' in sys.argv
M3='--m3' in sys.argv or M32
work=root/('build/rts-fatfs-test-m32' if M32 else 'build/rts-fatfs-test-m3' if M3 else 'build/rts-fatfs-test');work.mkdir(parents=True,exist_ok=True)
stage=Path(__file__).parent
for name in ('ff.c','ff.h','ffconf.h','diskio.h','ffunicode.c'):
    target=work/'fat'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(root/'arm7/source/fat'/name,target)
for name in ('RtsSnapshotPrepare.cpp','RtsSnapshotPrepare.h'):
    shutil.copyfile(root/'arm7/source/loader'/name,work/name)
shutil.copyfile(root/'common/RtsSnapshotInfo.h',work/'RtsSnapshotInfo.h')
(work/'common.h').write_text('#pragma once\n#include <cstdint>\nusing u32=uint32_t;\n')
harness=stage/'fatfs_harness.cpp'
if not harness.exists():harness=root/'tests/rts_fatfs_harness.cpp'
shutil.copyfile(harness,work/'harness.cpp')
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
cxx=os.environ.get('CXX','C:/msys64/mingw64/bin/g++.exe' if os.name=='nt' else 'g++')
for name in ('ff','ffunicode'):
    subprocess.run([cc,'-std=c17','-O2','-I'+str(work/'fat'),'-c',str(work/'fat'/(name+'.c')),'-o',str(work/(name+'.o'))],check=True)
exe=work/('test.exe' if os.name=='nt' else 'test')
subprocess.run([cxx,'-std=c++23','-static','-DPICO_RTS_SNAPSHOT',*(['-DPICO_RTS_ARM7_CAPTURE'] if M3 else []),*(['-DPICO_RTS_VIDEO_CAPTURE'] if M32 else []),'-I'+str(work),str(work/'harness.cpp'),str(work/'RtsSnapshotPrepare.cpp'),str(work/'ff.o'),str(work/'ffunicode.o'),'-o',str(exe)],check=True)
image=work/'isolated-fat32.img'
sectors=131072;fat_sectors=1024
boot=bytearray(512);boot[0:3]=b'\xeb\x58\x90';boot[3:11]=b'MSWIN4.1'
struct.pack_into('<HBHBHHBHHHII',boot,11,512,1,32,2,0,0,0xf8,0,63,255,0,sectors)
struct.pack_into('<IHHIHH',boot,36,fat_sectors,0,0,2,1,6)
boot[64]=0x80;boot[66]=0x29;struct.pack_into('<I',boot,67,12345678)
boot[71:82]=b'RTS-M2-TEST';boot[82:90]=b'FAT32   ';boot[510:512]=b'\x55\xaa'
info=bytearray(512);struct.pack_into('<I',info,0,0x41615252);struct.pack_into('<III',info,484,0x61417272,0xffffffff,3);struct.pack_into('<I',info,508,0xaa550000)
with image.open('wb') as f:
    f.truncate(sectors*512)
    for n,b in [(0,boot),(6,boot),(1,info),(7,info)]:f.seek(n*512);f.write(b)
    for start in (32,32+fat_sectors):f.seek(start*512);f.write(struct.pack('<III',0x0ffffff8,0xffffffff,0x0fffffff))
subprocess.run([str(exe),str(image)],check=True,timeout=30)
