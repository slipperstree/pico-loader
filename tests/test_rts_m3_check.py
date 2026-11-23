"""Read-only M3 checker accepts actual model output and rejects damaged sections."""
import importlib.util,json,struct,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('checker',r/'tools/check_rts_snapshot.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
f=r/'build/rts-worker-m3';results=[]
for name in ('model-snapshot.bin','model-snapshot-fast.bin'):
 result=c.check(f/name);assert result['arm7']['private_bytes']==65536 and result['arm7']['shared_bytes']==32768
 results.append(result);print('PASS M3 checker:',name)
original=(f/'model-snapshot-fast.bin').read_bytes()
for label,offset,crc_again in [('private WRAM corruption',512+0x40c200,False),('context frame mismatch',512+0x40c000+32,True),('incomplete header',16,False),('unsupported WRAM',512+0x40c000+20,True)]:
 blob=bytearray(original);blob[offset]^=1
 if crc_again:struct.pack_into('<I',blob,24,zlib.crc32(blob[512:]))
 path=f/'model-invalid.bin';path.write_bytes(blob)
 try:c.check(path)
 except ValueError:print('PASS rejects',label)
 else:raise AssertionError('Accepted '+label)
(f/'checker-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
