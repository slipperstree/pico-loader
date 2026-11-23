# M3.2: original display-memory capture

M3.1 passed hardware capture on the same 414/MSET 3DS/A2GJ target. This version
adds the next missing data section; it still does not implement game-state load.

Build with `PICO_RTS_SNAPSHOT=1 PICO_RTS_ARM7_CAPTURE=1 PICO_RTS_VIDEO_CAPTURE=1`.
Outputs use `_capture_m32` and `build/rts-worker-m32`, leaving previous builds
intact. New file: `/_pico/RTS-A2GJ-M3V.bin`, 5,019,136 bytes / 9803 sectors.
Payload is 9802 sectors. Magic 32565452, version 00030002. Older files are not
resized or overwritten; a new-format capture must be made.

The first 424200 hex payload bytes retain M3.1's RAM/TCM/ARM7 sections. Next:

| File offset (hex) | Bytes | Contents |
| --- | ---: | --- |
| 424400 | 512 | VDC1 display metadata |
| 424600 | 671744 | Physical VRAM A-I, in ascending LCDC-address order |
| 4C8600 | 2048 | Standard A/B BG/OBJ palettes |
| 4C8E00 | 2048 | A/B OAM |

Metadata stores original DISPCNT, gate-saved brightness, VRAM controls A-I,
power/WRAM controls and readable BG control registers. It does not bulk-dump
write-only scrolling/affine registers or claim to capture hidden 3D state.

Each VRAM read maps exactly one bank into its physical LCDC aperture, reads
one sector and restores the live control before returning. It never writes
VRAM, palettes or OAM. For bank C, the 96x8 progress pixels are substituted
from the original backup into the output buffer, so file bytes contain game
pixels. The live progress framebuffer remains usable while capturing.

Bank C/D assigned to ARM7 is declined before any display/SD operation: these
banks might hold ARM7 code or stacks. The existing three brightness flashes
report this refusal without remapping a bank. Source byte 04000247 (WRAMCNT)
is deliberately skipped when touching the non-contiguous VRAM controls.

Workspace: 12288 bytes, validated by the real target's installer. All previous
ARM7 guards, CRC/fast mode, card ownership and sector deadlines remain.

Validation executes actual compiled code: all 1320 display data sectors,
physical LCDC mapping checks before reads, exact original pixels with overlay
excluded, restored mappings, unchanged graphics memory, C/D and bounds guards.
The complete relocated ARM9 worker + ARM7 helper produces the correct extended
fast snapshot and CRC on a modeled sector device. The actual ROM installer,
dual-CPU handshake, ARM7 contexts/error paths and real FatFs preparation pass.
The desktop checker accepts the extended sections and rejects corrupt VRAM,
forged layout and unsupported ownership. M2/M3.1 checker regressions pass.

Hardware capture remains to be tested for M3.2. This is not restoration QA.
Remaining restore work includes ARM9 banked/CP15 state, write-only graphics
state, sound/IRQ/timer/IPC/hidden device state, file identity/preflight and safe
memory restoration plus coordinated CPU release. No load hotkey is enabled.

References: [GBATEK DS memory/VRAM mapping](https://mgba-emu.github.io/gbatek/).
The local BlocksDS/libnds video header also exposes save/restore of VRAM
mapping controls. No external emulator save-state code is copied.
