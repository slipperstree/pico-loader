"""Native tests for the freestanding four-slot renderer/controller.
No pause, capture, filesystem or live loader integration is claimed here.
"""
from pathlib import Path
import ctypes as C,json,os,random,subprocess,sys
r=Path(sys.argv[1]).resolve();f=r/'build/rts-menu';f.mkdir(parents=True,exist_ok=True)
cc=os.environ.get('CC','C:/msys64/mingw64/bin/gcc.exe' if os.name=='nt' else 'gcc')
dll=f/('menu.dll' if os.name=='nt' else 'menu.so')
subprocess.run([cc,'-shared','-O2','-Wall','-Wextra','-Werror',*(['-Wl,--export-all-symbols'] if os.name=='nt' else ['-fPIC']),'-I'+str(r/'common'),str(r/'runtime/rts/menu/MenuState.c'),str(r/'runtime/rts/menu/MenuRender.c'),'-o',str(dll)],check=True)
class Time(C.Structure):_fields_=[('year',C.c_uint16),('month',C.c_uint8),('day',C.c_uint8),('hour',C.c_uint8),('minute',C.c_uint8),('second',C.c_uint8),('reserved',C.c_uint8)]
class Slot(C.Structure):_fields_=[('occupied',C.c_uint8),('reserved',C.c_uint8*3),('time',Time)]
class Menu(C.Structure):_fields_=[('slots',Slot*4),('previous_keys',C.c_uint16),('repeat_frames',C.c_uint16),('selected',C.c_uint8),('action',C.c_uint8),('phase',C.c_uint8),('debug_enabled',C.c_uint8),('wait_hotkey_release',C.c_uint8),('percent',C.c_uint8),('reserved',C.c_uint8*2)]
lib=C.CDLL(str(dll));lib.RtsMenuInit.argtypes=[C.POINTER(Menu),C.c_int];lib.RtsMenuTick.argtypes=[C.POINTER(Menu),C.c_uint16];lib.RtsMenuTick.restype=C.c_int
lib.RtsMenuSetProgress.argtypes=[C.POINTER(Menu),C.c_uint32,C.c_uint32];lib.RtsMenuFinish.argtypes=[C.POINTER(Menu)]
lib.RtsMenuFormatTime.argtypes=[C.POINTER(Time),C.c_char_p,C.c_char_p];lib.RtsMenuDebugEnabled.argtypes=[C.c_char_p,C.c_size_t]
Blit=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.POINTER(C.c_uint16),C.c_uint,C.c_uint,C.c_uint)
lib.RtsMenuRender.argtypes=[C.POINTER(Menu),C.POINTER(C.c_uint16),Blit,C.c_void_p,C.c_char_p]
def fresh(debug=1):
 m=Menu();lib.RtsMenuInit(C.byref(m),debug);return m
def tick(m,key):return lib.RtsMenuTick(C.byref(m),key)
def press(m,key):tick(m,0);return tick(m,key)
m=fresh();assert tick(m,0x301)==0 and m.phase==0;assert tick(m,1)==0 and m.phase==0
tick(m,0);press(m,1);assert m.phase==1 and m.action==1
for _ in range(100):assert tick(m,1)==0 and m.phase==1
assert press(m,1)==1 and m.phase==2
assert press(m,2)==0 and m.phase==2 # In-flight operation cannot be cancelled mid-apply.
lib.RtsMenuFinish(C.byref(m));assert m.phase==3 and m.percent==100
print('PASS hotkey release gate, fresh confirmation and busy-operation input isolation')
m=fresh();tick(m,0);order=[]
for _ in range(8):press(m,16);order.append(m.selected)
assert order==[1,2,3,0,1,2,3,0]
order=[]
for _ in range(4):press(m,32);order.append(m.selected)
assert order==[3,2,1,0]
assert press(m,64)==0 and m.selected==2;press(m,128);assert m.selected==0
for _ in range(1000):press(m,16);assert 0<=m.selected<4
print('PASS horizontal row transitions and wrap-around; vertical column-preserving selection')
for occupied in (0,1):
 m=fresh();tick(m,0);m.slots[0].occupied=occupied;press(m,1)
 assert m.phase==1 and m.action==(2 if occupied else 1)
 before=(m.selected,m.action);press(m,16);press(m,32);assert (m.selected,m.action)==before
 press(m,128);assert m.action==1
 press(m,64);assert m.action==(2 if occupied else 1)
 press(m,2);assert m.phase==0 and m.selected==0
 assert press(m,2)==3 and m.phase==3
print('PASS occupied defaults to Load, empty defaults to Save; action-menu directions and B navigation')
m=fresh();tick(m,0);press(m,16);initial=m.selected
for _ in range(17):tick(m,16)
assert m.selected==initial
tick(m,16);assert m.selected==(initial+1)%4
print('PASS directional hold-repeat without A-button auto-confirm')
date=C.create_string_buffer(11);clock=C.create_string_buffer(9);t=Time(2026,11,24,7,8,9,0)
lib.RtsMenuFormatTime(C.byref(t),date,clock);assert date.value==b'2026/11/24' and clock.value==b'07:08:09'
for value,expected in ((None,1),(b'on',1),(b'off',0),(b'  OFF\r\n',0),(b'0',0),(b'1',1),(b'\xef\xbb\xbfoff\r\n',0),(b'unknown',1)):
 assert lib.RtsMenuDebugEnabled(value,0 if value is None else len(value))==expected
print('PASS exact timestamp layout and default-on debug configuration parsing')
random.seed(6)
for total in (0,1,3,99,100,9803,2**32-1):
 for completed in (0,1,max(0,total-1),total,2**32-1,*[random.randrange(2**32) for _ in range(50)]):
  lib.RtsMenuSetProgress(C.byref(m),completed,total)
  assert m.percent==(0 if not total else min(100,completed*100//total)),(completed,total,m.percent)
print('PASS bounded percentage including 32-bit extremes and zero-length work')
@Blit
def thumbnail(user,slot,p,stride,x,y):
 for yy in range(60):
  for xx in range(80):
   red=(xx//10+slot*5)*4%32;green=(yy//10+slot*7)*4%32;blue=(xx//20+yy//20)*8%32
   p[(y+yy)*stride+x+xx]=0x8000|red|(green<<5)|(blue<<10)
def render(menu,name):
 n=256*192;canary=(C.c_uint16*(n+2))();canary[0]=0x1234;canary[n+1]=0x5678
 p=C.cast(C.byref(canary,2),C.POINTER(C.c_uint16));lib.RtsMenuRender(C.byref(menu),p,thumbnail,None,b'DEBUG S5 0128/9803')
 assert canary[0]==0x1234 and canary[n+1]==0x5678,'Frame write outside lower-screen memory'
 data=C.string_at(p,n*2);(f/(name+'.rgb555')).write_bytes(data);return data
m=fresh();tick(m,0)
for i in (0,2):m.slots[i].occupied=1;m.slots[i].time=Time(2026,11,24,14,12+i,9,0)
for selected in range(4):
 m.selected=selected;m.phase=0;render(m,'slot-'+str(selected))
 for action in (1,2):
  if action==2 and not m.slots[selected].occupied:continue
  m.phase=1;m.action=action;render(m,'action-'+str(selected)+'-'+str(action))
m.phase=2;m.action=1
for action in (1,2):
 m.action=action
 for debug in (0,1):
  m.debug_enabled=debug
  for percent in (0,25,50,75,100):m.percent=percent;render(m,'progress-'+str(action)+'-'+str(debug)+'-'+str(percent))
m.percent=50;m.debug_enabled=1;yes=render(m,'debug-on');m.debug_enabled=0;no=render(m,'debug-off')
assert yes!=no and yes[:170*256*2]==no[:170*256*2]
assert all(no[i:i+2]==b'\x00\x80' for i in range(170*256*2,len(no),2))
print('PASS renderer bounds, four-slot action layouts and debug-independent progress display')
if '--storyboard' in sys.argv:
 for mask in range(16):
  for i in range(4):m.slots[i].occupied=bool(mask&(1<<i));m.slots[i].time=Time(2026,11,24,14,12+i,9,0)
  for selected in range(4):
   m.selected=selected;m.phase=0;render(m,f'frame-{mask}-{selected}-0-0')
   for action in (1,2):
    if action==2 and not m.slots[selected].occupied:continue
    m.phase=1;m.action=action;render(m,f'frame-{mask}-{selected}-1-{action}')
 print('PASS generated all occupancy/selection/action preview frames using the production renderer')
results={'state_machine':'PASS','input_release_and_repeat':'PASS','timestamps':'PASS','debug_config':'PASS','progress':'PASS','renderer_bounds':'PASS','state_bytes':C.sizeof(Menu),'live_integration':False}
if '--arm' in sys.argv:
 prefix=os.environ.get('ARM_NONE_EABI_PREFIX','C:/msys64/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-' if os.name=='nt' else 'arm-none-eabi-')
 env=os.environ.copy()
 if os.name=='nt':env['PATH']=os.environ.get('WONDERFUL_TOOLCHAIN','C:/msys64/opt/wonderful')+'/bin;'+env['PATH']
 objects=[]
 for source in ('MenuState','MenuRender'):
  obj=f/(source+'.o');objects.append(str(obj))
  subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-Os','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-fstack-usage','-I'+str(r/'common'),'-c',str(r/'runtime/rts/menu'/(source+'.c')),'-o',str(obj)],env=env,check=True)
 elf=f/'menu-arm9.elf'
 subprocess.run([prefix+'gcc','-mcpu=arm946e-s','-marm','-nostdlib','-Wl,-e,RtsMenuInit',*objects,'-lgcc','-o',str(elf)],env=env,check=True)
 undefined=subprocess.check_output([prefix+'nm','-u',str(elf)],env=env,text=True).strip()
 assert not undefined,undefined
 print(subprocess.check_output([prefix+'size',str(elf.relative_to(r))],cwd=r,env=env,text=True).strip())
 results['arm9_compile_and_link']='PASS'
 print('PASS freestanding ARM9 link with compiler support library; no unresolved symbols')
(f/'results.json').write_text(json.dumps(results,indent=2))
