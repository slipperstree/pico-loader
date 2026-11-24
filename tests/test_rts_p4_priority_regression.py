"""Optional ordering regression against a separately preserved P4.5 build.
The guard encodes a worst-case bus contention assumption, not hardware timing.
Requires a private M3.2 capture and build/rts-worker-p45 runtime artifacts;
neither ROM/RAM bytes nor old build artifacts are checked into the repository.
"""
from pathlib import Path
import hashlib,json,struct,sys
r=Path(sys.argv[1]).resolve();model=r/'tests/test_rts_p4_worker.py'
sys.argv=[str(model),str(r),sys.argv[2],'--p43','--fast-io','--cache-check','--bus-check']
s=model.read_text(encoding='utf-8').split('disk={physical[0]:bytes(blank)}')[0]
s=s.replace("'build/rts-worker-p43'","'build/rts-worker-p45'")
g={'__file__':str(model)};exec(compile(s,str(model),'exec'),g)
try:g['make']({g['physical'][0]:bytes(g['blank'])})
except AssertionError as e:
 assert 'ARM9 shared main RAM access with ARM7 priority/server running' in repr(e.__cause__),(repr(e),repr(e.__cause__))
 cause=e.__cause__.args[0]
 pc=int(cause[3],16);offset=pc-g['base']
 assert struct.unpack_from('<I',g['image'],offset-4)[0]==0xe1cc10b0,'Expected IPC halfword write immediately before the guard stop'
 assert struct.unpack_from('<I',g['image'],offset)[0]==0xe580e0c0,'Expected first trace-45 main RAM store'
 failure=repr(e.__cause__)
 print('PASS preserved P4.5 binary violates explicit arbitration guard after start 8:',failure,flush=True)
else:raise AssertionError('Expected old binary to violate the arbitration guard')
old=r/'build/rts-worker-p45';new=r/'build/rts-worker-p43'
result={'hazard_model':'ARM7 running server from shared main RAM with priority bit 15 set','old_worker_sha256':hashlib.sha256((old/'worker.bin').read_bytes()).hexdigest(),'old_build_fingerprint':json.loads((old/'RtsM2Image.json').read_text())['p4_build_fingerprint'],'old_guard_failure':failure,'new_worker_sha256':hashlib.sha256((new/'worker.bin').read_bytes()).hexdigest(),'hardware_cause_confirmed':False}
(new/'arbitration-regression.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
