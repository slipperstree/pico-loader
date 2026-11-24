"""Verify incremental output equals a fresh frame and preserves untouched pixels."""
from pathlib import Path
import ctypes as C,os,subprocess,sys
r=Path(sys.argv[1]).resolve();f=r/'build/rts-menu';f.mkdir(parents=True,exist_ok=True)
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
dll=f/('dirty.dll' if os.name=='nt' else 'dirty.so')
subprocess.run([cc,'-shared','-O2','-Wall','-Wextra','-Werror',*(['-Wl,--export-all-symbols'] if os.name=='nt' else ['-fPIC']),'-I'+str(r/'common'),str(r/'runtime/rts/menu/MenuState.c'),str(r/'runtime/rts/menu/MenuRender.c'),'-o',str(dll)],check=True)
class Time(C.Structure):_fields_=[('year',C.c_uint16),('month',C.c_uint8),('day',C.c_uint8),('hour',C.c_uint8),('minute',C.c_uint8),('second',C.c_uint8),('reserved',C.c_uint8)]
class Slot(C.Structure):_fields_=[('occupied',C.c_uint8),('reserved',C.c_uint8*3),('time',Time)]
class Menu(C.Structure):_fields_=[('slots',Slot*4),('previous_keys',C.c_uint16),('repeat_frames',C.c_uint16),('selected',C.c_uint8),('action',C.c_uint8),('phase',C.c_uint8),('debug_enabled',C.c_uint8),('wait_hotkey_release',C.c_uint8),('percent',C.c_uint8),('reserved',C.c_uint8*2)]
class Paint(C.Structure):_fields_=[('previous',Menu),('debug',C.c_char*32),('initialized',C.c_uint8),('reserved',C.c_uint8*3)]
Pixels=C.c_uint16*(256*192)
Blit=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.POINTER(C.c_uint16),C.c_uint,C.c_uint,C.c_uint)
calls=[]
@Blit
def thumb(user,slot,p,stride,x,y):
 calls.append(slot)
 for yy in range(60):
  for xx in range(80):p[(y+yy)*stride+x+xx]=0x8000|((slot+1)<<5)|(xx&31)
lib=C.CDLL(str(dll));lib.RtsMenuInit.argtypes=[C.POINTER(Menu),C.c_int]
lib.RtsMenuRender.argtypes=[C.POINTER(Menu),C.POINTER(C.c_uint16),Blit,C.c_void_p,C.c_char_p]
lib.RtsMenuRenderUpdate.argtypes=[C.POINTER(Menu),C.POINTER(C.c_uint16),C.POINTER(Paint),Blit,C.c_void_p,C.c_char_p]
for mask in (0,5,15):
 m=Menu();lib.RtsMenuInit(C.byref(m),1)
 for i in range(4):m.slots[i].occupied=bool(mask&(1<<i));m.slots[i].time=Time(2026,11,25,8,9,10,0)
 cache=Paint();dirty=Pixels();clean=Pixels()
 def paint(line=b'DEBUG S5 0064'):
  calls.clear();lib.RtsMenuRenderUpdate(C.byref(m),dirty,C.byref(cache),thumb,None,line);actual=list(calls)
  lib.RtsMenuRender(C.byref(m),clean,thumb,None,line)
  assert bytes(dirty)==bytes(clean),(mask,m.phase,m.selected,m.action,m.percent)
  return actual
 paint()
 for selected in (1,2,3,0,3,2,1,0):
  m.selected=selected;assert not paint(),'Navigation re-read a thumbnail'
  m.phase=1;m.action=2 if m.slots[selected].occupied else 1;assert not paint()
  if m.slots[selected].occupied:
   m.action=1;assert not paint();m.action=2;assert not paint()
  m.phase=0;assert not paint()
 m.slots[2].occupied=not m.slots[2].occupied
 assert paint()==([2] if m.slots[2].occupied else [])
 m.phase=2;m.action=1;m.percent=0;paint()
 # Static regions and the already painted bar must not be erased/redrawn.
 dirty[0]=0x8123;m.percent=25
 lib.RtsMenuRenderUpdate(C.byref(m),dirty,C.byref(cache),thumb,None,b'DEBUG S5 0250')
 assert dirty[0]==0x8123;dirty[0]=0x8000;paint(b'DEBUG S5 0250')
 at=94*256+26;dirty[at]=0x8123;m.percent=50
 lib.RtsMenuRenderUpdate(C.byref(m),dirty,C.byref(cache),thumb,None,b'DEBUG S5 0500')
 assert dirty[at]==0x8123,'Progress repainted its completed segment';dirty[at]=0x83e0;paint(b'DEBUG S5 0500')
 for percent in (50,51,75,99,100,70,10,0):m.percent=percent;paint()
 for line in (b'ERROR 1009   PRESS B',b'DEBUG L2 0100',b'',None):paint(line)
 m.debug_enabled=0;paint();m.debug_enabled=1;paint()
 m.action=2;paint();m.phase=0;paint()
print('PASS dirty/full equivalence, no thumbnail reads on key navigation, persistent static pixels and incremental progress')
