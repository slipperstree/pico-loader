# P4 persistent save/load experiment

P4 connects the existing state primitives to live DSPico hotkeys for one
host-verified A2GJ ROM/SDK 3.1 profile. It is an opt-in research build, not a
general save-state release. Hardware restore validation is pending.

Save uses L+R+Down+A; load uses L+R+Down+B, held for 30 VBlanks. A single
`game.rts` file is preallocated beside `game.nds`, preserving UTF-8 paths and
the basename. A completed slot persists across reboot; missing/incomplete
slots show `NO SAVE B` and return only after a fresh B press. Multiple folders
with the same ROM basename have independent slots. Multi-slot UI is future work.

## P4.5: distinguish the C renderer return from the IPC transfer

Hardware P4.4 last showed S2 0041. This precedes the waiting loop and its
deadline. The display is updated inside the renderer; this does not prove
that the renderer returned or ARM7 saw start 8. The exact cause is unknown.
M3.2 used the original private-WRAM capture server; P4 changes the protocol,
stack, audio/FIFO preflight and CPU capture. Working save behavior regressed;
this does not establish a hardware limitation or general ARM7 failure.

The IPC transfer now uses an ARM leaf with no stack use, C call or callee-saved
register dependence. Optional stackless stamps are S2 0043 (entered after
C renderer returned), 0044 (IPCSYNC read completed), and 0045 (write completed).
Only IRQ-enable bit 14 is retained when publishing 8. A separate readback
checks the local outgoing nibble and holds with 8128 if it does not latch.
The subsequent C marker is still 0042: these IDs are not monotonic progress.

Tests execute the actual leaf with both IRQ-enable states and all 16 incoming
nibbles, verifying its halfword transfer, trace order and callee-saved ABI.
The combined worker executes its ARM/Thumb veneer. Local models do not
reproduce physical bus stalls and do not prove a physical fix.
This remains save-only, with the same format and basename.

## P4.4: bound the cache-off ARM7 start and expose peer checkpoints

Hardware P4.3 reached S2 0033: CPU capture and the fused cache transition
completed, but the subsequent start call did not return. The returned slot is
still phase 0 / sequence 0, with an all-zero payload. No snapshot was written.

The start wait now uses direct volatile accesses: D-cache and write buffering
are already off, so per-iteration cache invalidation and the initial drain are
unnecessary. A local VCOUNT deadline (180 scanline wraps, about three seconds)
plus a finite spin fallback bounds this loop without relying on the ARM7 clock.
This removes unnecessary maintenance; it does not establish it as the cause.

The trace build adds S2 0040 (entry), 0041 (ready cleared), and 0042 (start 8
sent). ARM7 publishes IPCSYNC checkpoints, displayed by ARM9 as S2 0061..0070:
received start, saved registers, switched stack, before capture, System bank,
SVC bank, FIQ bank, capture returned, C loop entry, audio/FIFO preparation done.
Fast transitions may be skipped on screen. S2 0072 means peer remains at C.
If readiness is not published before the deadline, S9 8100 + last peer nibble
holds both CPUs without SD writes; e.g. 8112 means no advance from C. This is a
diagnostic hold, not a resumable error screen. Do not keep waiting for card I/O.

Tests execute all ten ARM7 checkpoints through the actual private hook and
verify its original IRQ frame/epilogue ABI. The ARM9 model rejects cache
maintenance during this start wait and verifies the no-ready timeout without
card writes. The build remains save-only (load refuses with 1007) and reserves
18944 bytes within the existing 20 KiB arena. Physical verification is pending.

## P4.3: S2 trace and fused cache transition

Hardware P4.2 reached dimming and S2 0000, then stopped. The returned slot
remains phase 0 / sequence 0, with no payload written. This narrows the boundary
to ARM9 CPU capture, cache switching, or the subsequent explicit ARM7 start.

Disassembly of that exact P4.2 worker proves two stack stores (`sp+12`, `sp+20`)
and header stores after `flushCaches` returns and before disabling D-cache.
Those new dirty values need not reach backing RAM when D-cache is disabled.
The prior model treated all stores as immediately visible backing memory.
An extended model catches the old binary's post-clean writes before card I/O.
This is a definite defect, not conclusive proof of the unique hardware hang.

`rtsFlushCachesAndEnter` now pushes/saves arguments before cleaning and performs
the entire clean + cache-control switch in one ARM primitive. No C call or new
stack store intervenes. Optional stamp 31 only uses disposable CPU-record
padding and uncached VRAM; the model discards those cached padding stores at
the transition and checks no live stack/header data is lost.

The opt-in `PICO_RTS_CPU_TRACE=1` artifact has separate loader/object directories.
It is save-only; the load hotkey refuses with 1007. Unlinked load code makes room
for 28 stackless assembly stamps plus C boundary markers 29..35 within the
existing first-target arena ceiling. Each stamp preserves scratch registers,
banked LR and flags in padding; it never pushes onto an arbitrary mode stack.
The complete captured 512-byte state matches the uninstrumented primitive.

Steps 1..8 cover mode banks; 9..27 cover the 19 CP15 reads; 28 publishes the
record; 29 returns to C; 30 completes header metadata; 31 completes the clean;
32 disables D-cache; 33 requests ARM7 start; 34 sees ready; 35 completes payload
preflight. The register encodings were checked against the
[ARM946E-S Technical Reference Manual](https://documentation-service.arm.com/static/5e8e3ee588295d1e18d3aa82).
The exact last hardware stamp, not just broad S2, is still required.

## P4.2: defer capture until visible ARM9 feedback

P4.1 also froze on hardware with no dimming and no progress. Its returned
slot is the identical phase-0, sequence-0, all-zero payload file. Loader hashes
match the deployed P4.1. The new S0/ready timeout did not get a chance to run.
The exact hardware cause remains unconfirmed.

P4.2 keeps the new operation selection in private WRAM and removes P4 context
capture/shared-ready writes before publishing C. After C, ARM7 waits in private
assembly for a separate IPCSYNC start nibble 8. ARM9 first dims, reaches S0/S2,
captures its original control state, flushes caches and turns off D-cache/write
buffering. Only then does it clear ready and publish 8. ARM7 switches stacks,
captures the original private game frame and samples sound/FIFO state; ARM9
waits for readiness with the existing bounded S9 0081 failure path. Both normal
and early-cancel paths retain the original private epilogue ABI. Early refusal
does not replay queues that ARM7 has not drained.

The capture primitive now explicitly records its supplied parked SP in the
active bank; calling it from a scratch stack must not publish that scratch SP
as the saved IRQ continuation. The argument frame preserves original IPC,
private SP, CPSR, IME and operation. The ARM7 loop accepts nibble 8 during the
brief prepared-to-running transition.

Tests assert that before C there are no new main-RAM writes (only the legacy
guard word), no capture, and no new shared operation publication. They execute
the explicit start transition and compare original IRQ SP/frame after deferred
capture. ARM9's model asserts S2 and D-cache off before starting ARM7, and checks
the timeout without card writes. Hardware must still verify this boundary.

## P4.1: first hardware pause failure

On 414 hardware, P4.0 froze after the save hotkey without a visible progress
line. The returned `.rts` is still phase 0, sequence 0, with an all-zero
payload; no snapshot transaction was started. This does not establish the
later capture-service bug below as the cause of this early hardware freeze.

The actual Thumb ARM7 RPC command-1 call was not covered by the earlier
combined model (its Python peer called the ARM helper directly). Executing
that call reproduces an ARM service being entered in Thumb mode: missing ELF
function types prevented an interworking veneer. Both capture assembly
entries are now typed and command 1 is exercised through the real C loop.

ARM7's C preflight now runs on its independent main-RAM stack after C is
published. The private hook clears a pause-ready flag before publishing C;
ARM7 publishes ready only after sampling audio/FIFO state. ARM9 opens its
guarded progress display at S0 and waits for this flag with a finite budget.
Missing readiness shows S9 0081 before card writes, instead of an unlimited
unobservable wait. Early refusal restores the temporary display correctly.

Tests select ARM946 and an ARMv4T surrogate (TI925T) for ARM9/ARM7 respectively.
The real outer ARM9 wrapper reaches S0; commands 1..5 run through the real
ARM7 loop; the missing-ready path fails closed without card writes. ARM7's
observed maximum stack is 72 of 384 bytes. The fixed arena remains 20480
bytes; CPU9-owned flags share their own cache line to retain the memory budget.
The full restore/refusal matrix remains covered. Physical pause/save still
needs another test; do not infer hardware success from these local models.

The two-to-three-second delay before the launch prompt is consistent with
the new program fingerprint and, on first launch, file preallocation. Those
checks are retained. No full-ROM hash is performed on each boot.

## Fixed file and identity

RTP0 / 0x40001 uses a 512-byte header and 0x4c9600-byte payload: the M3.2
regions plus a 512-byte sound shadow. Flags 4/6 identify this experiment;
diagnostic flags 1/3 cannot authorize restore. The header CRC at byte 480 is
calculated with that word zero. Payload CRC is required, including fast save
mode; fast only skips the additional console readback after writing.

Header words 54..99 hold the first 184 bytes of ARM9 CPU state; 100..107
hold the loaded-code fingerprint, 108..115 the worker/hook/loader build
fingerprint, and 116..119 are reserved zeros, not a boot-session gate.
The preparer validates and preserves completed headers instead of invalidating
them at every boot. No fresh-slot flag or last-saved sequence restricts loading.

The program fingerprint hashes `P4A2GJ\0\0`, little-endian ROM length,
the original 0x170-byte header, raw loaded ARM9 and raw loaded ARM7, in order.
It does not cover every ROM asset. The exact private test ROM's full SHA-256
is checked on the host by the installer test and before TF deployment. A full
32MiB ARM7 SHA scan on every boot was removed: the actual compiled SHA test
counted 462380 instructions per 4096 bytes (over 113 seconds for 32MiB even
at the unrealistic one instruction per 33.5MHz cycle, before SD wait states).

## Pause and restore

The ARM7 VBlank hook observes two SDK sound setters. Original SDK instructions,
registers, flags and stack ABI are preserved; busy covers the entire setter.
Both CPUs mask interrupts, check DMA/card/capture guards, and retain FIFO data
instead of clearing it. CPU-owned shared buffers avoid dirty-cache overwrite.

ARM7 switches to a separate main-RAM stack before any private WRAM restore.
The request/completed mailbox services capture, sector writes, FIFO replay,
muted sound preparation, and final release. Once destructive writes begin,
ARM7 cannot unwind through its overwritten private stack.

ARM9 validates identity, header/layout/CPU state, complete payload CRC,
file-backed ARM9/ARM7 continuations and sound coverage before applying data.
It then restores main RAM excluding its 20KiB reserved arena, TCM, ARM7 WRAM,
VRAM, palettes and OAM. A second read failure holds both CPUs. The saved FIFO
queues and audio are prepared before coherent release. Sound restarts from
recorded parameters; sample playback position is not restored.

The final ARM9 tail runs in trusted secure RAM, with its 76-byte context in
the dead saved game frame, so closing MPU region 2 never requires reading
the now-protected worker. ARM/Thumb entry symbols are explicitly typed; GNU
ld interworking veneer literals are validated and relocated even though they
have no emitted ABS32 relocation. The image builder rejects arena >0x5000.

## Limits and hardware test

Internal 3D geometry state, unobserved write-only display registers, exact
timer reload/phase and every hardware interrupt edge are not fully restored.
The first target uses a conservative layout/control compatibility check;
different CPU/display/timer configurations are refused. This is not a claim
that all game scenes or cross-boot transitions work. Begin with ordinary
dialogue, test save/advance/load, then reboot/re-enter and load the same file.
The `.sav` file already written to TF is not rolled back by a RAM checkpoint.
There is one slot; a failed overwrite can invalidate that experimental slot.

## Validation

Build with `PICO_RTS_SNAPSHOT=1 PICO_RTS_ARM7_CAPTURE=1
PICO_RTS_VIDEO_CAPTURE=1 PICO_RTS_RESTORE_PROBE=1`.

- `test_rts_identity.py`: native and compiled ARM7 SHA padding/streaming;
  UTF-8 basename/extension handling and bounded no-write path failures.
- `test_rts_snapshot_prepare.py --p4`: real FatFs in an isolated FAT32 image;
  Chinese paths, completed-header preservation across simulated boot,
  fragmentation and foreign-file protection.
- `test_rts_real_installer.py --p4`: actual installer/allocators on separately
  supplied, full-hash-verified ROM; all five wait hooks, private audio hooks,
  the secure tail and exactly 20480 reserved bytes.
- `test_rts_p4_arm7.py`: actual private VBlank hotkeys and main-RAM RPC
  loop, independent stack, sound/FIFO preparation, direct saved IRQ return.
- `test_rts_p4_worker.py`: actual worker save and restore in a new runtime
  with mutated state, all main/TCM bytes except dead handoff frame and arena,
  19 CP15 registers, general registers, SP/LR/CPSR, WRAM and original VRAM.
  Sector callbacks speed the failure matrix; a separate restore-only run
  executes the actual worker's SD protocol. Maximum observed ARM9 stack is
  824/1024 bytes. Wrong identity/corrupt payload preserve current RAM;
  missing slot prompts; destructive read failure never resumes.
- Real SDK PCM/timer hooks match original writes and ABI for all 16 channels;
  the existing M3.2 fast capture regression still passes.

Private ROM/capture/model bytes stay outside the source tree and release
package. These models do not emulate physical DSPico SD latency, cache/MPU
hardware, internal audio progress or GPU geometry. No public feature PR has
been sent before hardware restore testing.
