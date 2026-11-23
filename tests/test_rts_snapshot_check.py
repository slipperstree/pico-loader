"""Check actual worker-model output files, including deliberately corrupt fast data."""
import importlib.util,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('checker',root/'tools/check_rts_snapshot.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
folder=root/'build/rts-worker'
full=checker.check(folder/'model-snapshot.bin');fast=checker.check(folder/'model-snapshot-fast.bin')
assert full['console_full_readback'] and not fast['console_full_readback']
assert full['desktop_payload_crc_verified'] and fast['desktop_payload_crc_verified']
assert fast['timing_frames']['readback']==0 and full['timing_frames']['readback']>0
try:checker.check(folder/'model-snapshot-fast-corrupt.bin')
except ValueError as e:assert 'CRC32' in str(e)
else:raise AssertionError('Corrupt fast payload was accepted')
blob=bytearray((folder/'model-snapshot-fast.bin').read_bytes());struct.pack_into('<I',blob,17*4,123)
fake=folder/'model-forged-readback.bin';fake.write_bytes(blob)
try:checker.check(fake)
except ValueError as e:assert '伪造' in str(e)
else:raise AssertionError('Fast mode falsely claimed full readback')
print('PASS checker accepts full/fast actual payload CRC, reports timing, rejects corrupt data and forged readback')
