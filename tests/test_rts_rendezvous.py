"""Execute the built ARM patches, including relocations, against an IPCSYNC model.

This checks CPU/control-flow invariants, not Nintendo hardware, DMA or sound.
"""
import os, struct, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'pydeps'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

args = [arg for arg in sys.argv[1:] if arg != '--m2']
root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
toolchain = os.environ.get('WONDERFUL_TOOLCHAIN', 'C:/msys64/opt/wonderful' if os.name=='nt' else '/opt/wonderful')
prefix = os.environ.get('ARM_NONE_EABI_PREFIX', str(Path(toolchain)/'toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-'))
M2 = '--m2' in sys.argv
elf = root/('build/picoLoader9_DSPICO_snapshot_m2.elf' if M2 else 'build/picoLoader9_DSPICO_rts_probe.elf')
syms = {}
for line in subprocess.check_output([prefix+'nm', str(elf)], text=True).splitlines():
    p = line.split()
    if len(p) == 3:
        syms[p[2]] = int(p[0], 16)
sections = ['gate', 'guard', 'park', 'dim', 'resume']
blobs, bases, addresses = {}, {}, {}
scratch = root/'build/rts-asm-test'
scratch.mkdir(exist_ok=True)
for i, name in enumerate(sections + ['arm7']):
    sec = 'patch_rts7' if name == 'arm7' else 'patch_rts9_'+name
    path = scratch/(sec+'.bin')
    subprocess.run([prefix+'objcopy','--dump-section',sec+'='+str(path),str(elf)],check=True)
    blobs[name] = bytearray(path.read_bytes())
    bases[name] = 0x02010000 + i*0x1000 if name != 'arm7' else 0x03804000
    for symbol, value in syms.items():
        if syms['__start_'+sec] <= (value & ~1) < syms['__stop_'+sec]:
            addresses[symbol] = bases[name] + (value - syms['__start_'+sec])
    if name != 'arm7':
        assert len(blobs[name]) <= 124, (name, len(blobs[name]))

def patch(name, symbol, value):
    at = addresses[symbol] - bases[name]
    struct.pack_into('<I', blobs[name], at, value)

for block, literal, symbol in [
    ('gate','rts9_guard_address','rts9_guard'),
    ('guard','rts9_guard_return','rts9_return'),
    ('guard','rts9_park_address','rts9_park'),
    ('park','rts9_park_return','rts9_return'),
    ('park','rts9_dim_address','rts9_dim'),
    ('park','rts9_resume_address','rts9_resume'),
    ('dim','rts9_dim_resume','rts9_resume'),
    ('resume','rts9_resume_return','rts9_return')]:
    patch(block,literal,addresses[symbol])
patch('gate','rts9_enabled',1)
HOTKEY=struct.unpack_from('<I',blobs['arm7'],addresses['rts7_hotkey']-bases['arm7'])[0]
assert HOTKEY==0x381, 'User requested L+R+Down+A'
WORKER=0x02020000
if M2:patch('dim','rts9_m2_entry',WORKER)

REGS = [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
        UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
        UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
IPC,IME,BRIGHT,SUBBRIGHT = 0x04000180,0x04000208,0x0400006c,0x0400106c
DONE = 0x020f0000

class Bus:
    def __init__(self):
        self.out = [0,0]
        self.control = [0x4000,0x4000]
        self.events = []
        self.vcount = 192
        self.keys = 0x3ff
        self.card_busy = False
        self.dimmed = False
        self.frames=0
        self.worker_ticks=0
        self.snapshots=0

class CPU:
    def __init__(self, bus, side, mode=0x1f, thumb=False):
        self.bus, self.side = bus, side
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x02000000,0x400000)
        self.u.mem_map(0x03800000,0x10000)
        self.u.mem_map(0x04000000,0x2000)
        for name, blob in blobs.items():
            self.u.mem_write(bases[name], bytes(blob))
        self.u.mem_write(WORKER,b'\x1e\xff\x2f\xe1')
        self.u.mem_write(DONE,b'\x70\x47')
        self.initial_cpsr = 0xa0000000|mode
        self.u.reg_write(UC_ARM_REG_CPSR,self.initial_cpsr)
        self.sp = 0x023ff000 if side == 0 else 0x0380f000
        self.u.reg_write(UC_ARM_REG_SP,self.sp)
        self.initial_regs = [0x12340000+i for i in range(13)]
        for r,v in zip(REGS,self.initial_regs): self.u.reg_write(r,v)
        self.u.reg_write(UC_ARM_REG_LR,DONE|1)
        self.write(IME,1)
        self.write(BRIGHT,0x4003,2)
        self.write(SUBBRIGHT,0x8002,2)
        self.done=False
        self.thumb=thumb
        self.fault=False
        self.u.hook_add(UC_HOOK_CODE,self.code)
        self.u.hook_add(UC_HOOK_MEM_READ,self.read_mmio)
        self.u.hook_add(UC_HOOK_MEM_WRITE,self.write_mmio)

    def write(self,addr,value,size=4): self.u.mem_write(addr,int(value).to_bytes(size,'little'))
    def read(self,addr,size=4): return int.from_bytes(self.u.mem_read(addr,size),'little')
    def code(self,u,addr,size,data):
        if M2 and addr==addresses['rts7_m2_fault']:
            self.fault=True;u.emu_stop();return
        if M2 and self.side==0 and addr==WORKER:
            assert self.bus.out[1]==12 or self.bus.worker_ticks>600
            self.bus.worker_ticks+=1
            if self.bus.worker_ticks<=600:
                self.bus.out[0]=9 if self.bus.worker_ticks%2 else 10
                u.emu_stop();return
            if self.bus.worker_ticks==601:
                assert self.bus.frames>180, self.bus.frames
                assert self.bus.out[1]==12
                self.bus.out[0]=13;self.bus.events.append((0,13));self.bus.snapshots+=1
            if self.bus.out[1]==12:u.emu_stop();return
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        if addr == DONE:
            self.done=True
            u.emu_stop()
    def read_mmio(self,u,access,addr,size,value,data):
        if addr==IPC:
            self.write(IPC,self.bus.control[self.side]|(self.bus.out[self.side]<<8)|self.bus.out[1-self.side],2)
        elif addr==0x04000130:
            self.write(addr,self.bus.keys,2)
        elif addr==0x040001a4:
            self.write(addr,0x80000000 if self.bus.card_busy else 0)
        elif addr==0x04000006:
            previous=self.bus.vcount
            self.bus.vcount=(self.bus.vcount+17)%263
            if self.bus.vcount<previous:self.bus.frames+=1
            self.write(addr,self.bus.vcount,2)
    def write_mmio(self,u,access,addr,size,value,data):
        if addr==IPC:
            self.bus.out[self.side]=(value>>8)&15
            assert value&0x4000, 'IPCSYNC IRQ control was lost'
            self.bus.events.append((self.side,self.bus.out[self.side]))
        elif addr in (BRIGHT,SUBBRIGHT) and value==0x8008:
            assert self.bus.out==[10,12], ('dimmed before both CPUs parked',self.bus.out)
            self.bus.dimmed=True
        elif 0x040001a0 <= addr < 0x040001c0:
            raise AssertionError('Probe attempted cartridge/SD command')

    def start(self):
        self.done=False
        if self.side:
            self.write(self.sp,0xdeadbeef)
            self.write(self.sp+4,DONE|1)
            self.u.reg_write(UC_ARM_REG_SP,self.sp)
            self.u.reg_write(UC_ARM_REG_PC,addresses['rts7_thumb' if self.thumb else 'rts7_arm'] | int(self.thumb))
            self.u.reg_write(UC_ARM_REG_CPSR,self.initial_cpsr | (0x20 if self.thumb else 0))
        else:
            self.u.reg_write(UC_ARM_REG_PC,addresses['rts9_gate'])

    def step(self,count=100):
        if not self.done:
            pc=self.u.reg_read(UC_ARM_REG_PC)
            if self.u.reg_read(UC_ARM_REG_CPSR)&0x20: pc|=1
            self.u.emu_start(pc,0,count=count)

    def run(self,limit=100000):
        for _ in range(limit//100):
            self.step()
            if self.done:return
        raise AssertionError('Probe did not return within test instruction budget')

    def check(self):
        if self.side:
            assert [self.u.reg_read(r) for r in REGS[2:]]==self.initial_regs[2:]
            assert self.u.reg_read(UC_ARM_REG_SP)==self.sp+8
            assert self.u.reg_read(UC_ARM_REG_CPSR)&0xdf==self.initial_cpsr&0xdf
        else:
            assert [self.u.reg_read(r) for r in REGS]==self.initial_regs
            assert self.u.reg_read(UC_ARM_REG_SP)==self.sp
            assert self.u.reg_read(UC_ARM_REG_LR)==DONE|1
            assert self.u.reg_read(UC_ARM_REG_CPSR)&0xf00000df==self.initial_cpsr&0xf00000df
        assert self.read(IME)==1
        assert self.read(BRIGHT,2)==0x4003
        assert self.read(SUBBRIGHT,2)==0x8002

def call7(cpu):
    cpu.start();cpu.run();cpu.check()

for label,mode,request,busy,enabled,ime,out in [
    ('no request',0x1f,0,False,1,1,0),
    ('IRQ context',0x12,11,False,1,1,0),
    ('SVC context',0x13,11,False,1,1,0),
    ('IRQ masked',0x9f,11,False,1,1,0),
    ('cartridge busy',0x1f,11,True,1,1,0),
    ('disabled',0x1f,11,False,0,1,0),
    ('IME disabled',0x1f,11,False,1,0,0),
    ('IPCSYNC in use',0x1f,11,False,1,1,7)]:
    patch('gate','rts9_enabled',enabled)
    bus=Bus();bus.out=[out,request];bus.card_busy=busy
    cpu=CPU(bus,0,mode);cpu.write(IME,ime)
    cpu.start();cpu.run()
    assert not bus.dimmed and not bus.events
    if ime:cpu.check()
    else:
        assert cpu.read(IME)==0
        assert [cpu.u.reg_read(r) for r in REGS]==cpu.initial_regs
    print('PASS ARM9 guard:',label)
patch('gate','rts9_enabled',1)

patch('park','rts9_ready_budget',32)
bus=Bus();bus.out[1]=11;cpu=CPU(bus,0);cpu.start();cpu.run();cpu.check()
assert bus.out==[0,11] and not bus.dimmed
print('PASS ARM9 missing-peer timeout restores context')
patch('park','rts9_ready_budget',0x04000000)

for thumb in (False,True):
    bus=Bus();cpu=CPU(bus,1,thumb=thumb);call7(cpu)
    assert not bus.events
    bus.keys=0x3ff^HOTKEY
    for _ in range(29):call7(cpu)
    assert not bus.events
    call7(cpu)
    assert bus.out==[0,11]
    for _ in range(59):call7(cpu)
    assert bus.out==[0,0]
    for _ in range(40):call7(cpu)
    assert len(bus.events)==2, 'Held keys retriggered without a release'
    bus.keys=0x3ff;call7(cpu)
    bus.keys=0x3ff^HOTKEY
    for _ in range(30):call7(cpu)
    assert bus.out==[0,11]
    print('PASS ARM7',('Thumb' if thumb else 'ARM'),'epilogue, hold, withdrawal, rearm')

bus=Bus();bus.keys=0x3ff^HOTKEY
c7=CPU(bus,1);c9=CPU(bus,0)
for _ in range(30):call7(c7)
c9.start()
for _ in range(10):
    c9.step()
    if bus.out[0]==10:break
assert bus.out==[10,11]
c7.start()
for _ in range(3000):
    c7.step();c9.step()
    if c7.done and c9.done:break
assert c7.done and c9.done
c7.check();c9.check()
assert bus.dimmed and bus.out==[0,0],bus.events
expected=[(1,11),(0,10),(1,12)]+([(0,13)] if M2 else [])+[(1,0),(0,0)]
assert bus.events==expected,bus.events
print('PASS two-CPU request/ACK/park/release with restored CPU state and brightness')
for round_id in range(2):
    bus.worker_ticks=0;bus.frames=0
    bus.keys=0x3ff;call7(c7)
    bus.keys=0x3ff^HOTKEY
    for _ in range(30):call7(c7)
    c9.start()
    for _ in range(10):
        c9.step()
        if bus.out[0]==10:break
    c7.start()
    for _ in range(3000):
        c7.step();c9.step()
        if c7.done and c9.done:break
    assert c7.done and c9.done
    c7.check();c9.check()
    assert bus.out==[0,0]
    assert bus.events[-len(expected):]==expected
print('PASS three consecutive two-CPU rendezvous cycles')

if not M2:
    patch('dim','rts9_hold_budget',16)
    bus=Bus();bus.out[1]=12
    c9=CPU(bus,0)
    # Enter through the normal request path, then simulate ARM7 wedged after C.
    bus.out[1]=11;c9.start()
    for _ in range(10):
        c9.step()
        if bus.out[0]==10:break
    bus.out[1]=12;c9.run();c9.check()
    assert bus.out[0]==0 and bus.dimmed
    print('PASS ARM9 parked-peer watchdog restores brightness and interrupts')
    patch('dim','rts9_hold_budget',0x04000000)


for mode in (0x1f,0x12):
    bus=Bus();bus.keys=0x3ff^HOTKEY
    c7=CPU(bus,1,mode=mode)
    for _ in range(30):call7(c7)
    bus.out[0]=10;c7.start()
    for _ in range(10):
        c7.step()
        if bus.out[1]==12:break
    assert bus.out[1]==12
    bus.out[0]=0
    c7.run();c7.check()
    assert bus.out==[0,0]
    print('PASS ARM7 peer disappeared, original CPU mode restored:',hex(mode))

for out,busy in [(7,False),(0,True)]:
    bus=Bus();bus.keys=0x3ff^HOTKEY;bus.out[0]=out;bus.card_busy=busy
    c7=CPU(bus,1)
    for _ in range(40):call7(c7)
    assert bus.out==[out,0] and not bus.events
print('PASS ARM7 rejects busy cartridge and non-idle game IPCSYNC')
print('PASS section sizes:', {name:len(blob) for name,blob in blobs.items()})
print('Hardware, Nintendo SDK dispatch, caches, DMA, timers and sound are NOT simulated.')

bus=Bus();bus.keys=0x3ff^0x384
cpu=CPU(bus,1)
for _ in range(40):call7(cpu)
assert not bus.events
print('PASS old L+R+Down+Select combination does not trigger')
if M2:
    for guard in (0x040000b8,0x04000508):
        bus=Bus();bus.keys=0x3ff^HOTKEY;cpu=CPU(bus,1)
        for _ in range(30):call7(cpu)
        bus.out[0]=10
        cpu.write(guard,0x80000000 if guard==0x040000b8 else 0x80)
        call7(cpu)
        assert bus.out[1]==0
    print('PASS ARM7 DMA/sound-capture prechecks withdraw request without parking')
    patch('arm7','rts7_spin_budget',16)
    bus=Bus();bus.keys=0x3ff^HOTKEY;cpu=CPU(bus,1)
    for _ in range(30):call7(cpu)
    bus.out[0]=10;cpu.start()
    for _ in range(20):
        cpu.step()
        if cpu.fault:break
    assert cpu.fault and not cpu.done and cpu.read(IME)==0 and bus.out[1]==12
    print('PASS lost snapshot heartbeat holds ARM7 instead of resuming an unknown card transaction')
