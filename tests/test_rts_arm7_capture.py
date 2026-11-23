"""Validate ARM7 context/banked registers and all 192 staged WRAM sectors."""
import json,struct,sys
from pathlib import Path
from arm7_capture_model import Arm7CaptureModel,REGS
from unicorn.arm_const import *
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
folder=r/'build/rts-worker-m3';meta=json.loads((folder/'RtsM2Image.json').read_text());image=(folder/'worker.bin').read_bytes()
for mode in (31,18):
 a=Arm7CaptureModel(image,meta,mode=mode);h=struct.unpack('<128I',a.context)
 assert h[:6]==(0x31433741,1,a.parkSp,0xa0000000|mode,1,3)
 assert h[6:8]==(0,0) and h[8:20]==tuple(a.saved)
 assert h[20:38]==tuple(v for bank in a.banks for v in bank),(h[20:38],a.banks)
 assert h[38:43]==tuple(a.fiq) and not any(h[43:])
 for i in range(192):
  status,data=a.block(i,i+1);assert status==0
  src=a.beforePrivate if i<128 else a.shared
  at=(i if i<128 else i-128)*512
  assert data==src[at:at+512]
 before=bytes(a.u.mem_read(a.mailbox+32,512));a.writes=[]
 a.call('arm7_service',[a.mailbox]);assert not a.writes,'Duplicate request executed'
 status,data=a.block(192,193);assert status==1 and data==before
 a.u.mem_write(0x04000241,b'\x02');status,data=a.block(128,194)
 assert status==2 and data==before,'Wrong shared-WRAM mapping accepted'
 print('PASS ARM7 mode',hex(mode),'banked context, 192 exact sectors, guards, no game-memory writes')
for mode in (0,1,2):
 a=Arm7CaptureModel(image,meta,wram=mode)
 assert struct.unpack('<I',a.u.mem_read(a.mailbox+12,4))[0]==2
 print('PASS unsupported WRAM allocation refused:',mode)
(folder/'arm7-test-results.json').write_text(json.dumps({'arm7_system':'PASS','arm7_irq':'PASS','all_192_blocks':'PASS','bounds_duplicate_mapping_guards':'PASS','game_memory_unchanged':'PASS','hardware_tested':False},indent=2))
