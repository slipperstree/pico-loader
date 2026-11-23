"""Check actual M3.2 pipeline output and bounded metadata corruption."""
import importlib.util,json,struct,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('checker',r/'tools/check_rts_snapshot.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
f=r/'build/rts-worker-m32';path=f/'model-snapshot-fast.bin';result=c.check(path)
assert result['video']['vram_bytes']==0xa4000 and result['desktop_payload_crc_verified']
assert result['video']['display_main']=='00110800','Progress framebuffer DISPCNT leaked'
original=path.read_bytes()
for label,offset,fix in [('VRAM corruption',512+0x424400+0x40000,False),('video layout',51*4,False),('ARM7 owns C',512+0x424200+11*4,True)]:
 blob=bytearray(original)
 if label=='ARM7 owns C':struct.pack_into('<I',blob,offset,0x82)
 else:blob[offset]^=1
 if fix:struct.pack_into('<I',blob,24,zlib.crc32(blob[512:]))
 invalid=f/'model-invalid.bin';invalid.write_bytes(blob)
 try:c.check(invalid)
 except ValueError:print('PASS rejects',label)
 else:raise AssertionError('Accepted '+label)
(f/'checker-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('PASS M3.2 whole-file CRC, ARM7 frame, VRAM geometry and original display metadata')
