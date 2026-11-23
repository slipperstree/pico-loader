"""Read-only restore-readiness report. Diagnostic formats NEVER authorize load."""
import json,sys
from pathlib import Path
from check_rts_snapshot import check

def inspect(path):
    capture=check(path) # Includes whole-payload CRC and frame/layout validation.
    video=capture.get('video')
    flags=int(video['display_main'],16) if video else None
    configured_3d=None if flags is None else bool(flags&8 and flags&256 and (flags>>16)&3==1 and not flags&128)
    blockers=[
        'This is a diagnostic capture, not a loadable checkpoint format.',
        'Exact ROM/build/session identity and full-file preflight policy are missing.',
        'ARM9 banked/CP15 and coordinated two-CPU restore are incomplete.',
        'Write-only display state and sound/IRQ/timer/IPC/hidden device state are missing.'
    ]
    if configured_3d:
        blockers.append('Engine A is configured for enabled 3D BG0: VRAM alone does not establish recoverable geometry/render state.')
    elif configured_3d is None:
        blockers.append('No display metadata: a 2D-only restore assumption cannot be made.')
    return {'capture_integrity':capture['result'],'sequence':capture['sequence'],'payload_crc32':capture['payload_crc32'],
            'live_restore_allowed':False,'engine_a_3d_bg0_configured':configured_3d,
            'configuration_is_not_proof_of_nonempty_polygons':True,
            'blockers':blockers,'inspection_writes_game_memory':False}

if __name__=='__main__':
    try:print(json.dumps(inspect(sys.argv[1]),ensure_ascii=False,indent=2))
    except (ValueError,OSError,IndexError) as e:print('FAIL:',e);sys.exit(1)
