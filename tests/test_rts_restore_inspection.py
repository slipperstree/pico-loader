"""Valid diagnostic captures must stay blocked even when their CRC passes."""
import json,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
paths=[r/'build/rts-worker/model-snapshot-fast.bin',r/'build/rts-worker-m3/model-snapshot-fast.bin',r/'build/rts-worker-m32/model-snapshot-fast.bin']
if len(sys.argv)>2:paths.append(Path(sys.argv[2]))
for path in paths:
    report=json.loads(subprocess.check_output([sys.executable,str(r/'tools/inspect_rts_restore.py'),str(path)],text=True))
    assert report['capture_integrity']=='PASS' and report['live_restore_allowed'] is False
    assert report['blockers'] and not report['inspection_writes_game_memory']
    if path==paths[-1] and len(sys.argv)>2:assert report['engine_a_3d_bg0_configured'] is True
    print('PASS valid diagnostic remains blocked from live restore:',path.name)
