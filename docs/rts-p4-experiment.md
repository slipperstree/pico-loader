# P4 persistent save/load experiment

P4 connects the existing state primitives to live DSPico hotkeys for one
host-verified A2GJ ROM/SDK 3.1 profile. It is an opt-in research build, not a
general save-state release. Hardware restore validation is pending.

Save uses L+R+Down+A; load uses L+R+Down+B, held for 30 VBlanks. A single
`game.rts` file is preallocated beside `game.nds`, preserving UTF-8 paths and
the basename. A completed slot persists across reboot; missing/incomplete
slots show `NO SAVE B` and return only after a fresh B press. Multiple folders
with the same ROM basename have independent slots. Multi-slot UI is future work.

## P4.9: persistent restore with private ARM7 release

P4.8 hardware now passes the first save on the user's 414/MSET 3DS. The
returned slot is phase 2, sequence 7, with valid header and payload CRCs;
the recorded write duration is 970 frames (about 16 seconds). This confirms
the first-save repair, not hardware restore. The complete slot and loaders
are retained in private backups before updating the TF card.

P4.9 enables load with `PICO_RTS_LIVE_RESTORE=1` in addition to the four
capture/restore flags below. It is separate from `PICO_RTS_CPU_TRACE=1`.
The ARM7 shared-RAM server retains the save path's ARM9 main-RAM priority.
Restoring the game's ARM7 RAM priority while the server still fetches from
main RAM would reintroduce the hardware arbitration failure.

On restore, command 5 prepares devices and restarts samples, restores ARM7
registers, then enters a private-WRAM tail. The tail acknowledges with IPC
nibble 7 and performs no further main-RAM fetch or data read. Only after
that acknowledgement does ARM9 restore the original EXMEM and CPU state.
The 104-byte ARM9 secure tail publishes 6, waits for ARM7's zero acknowledgement,
clears its own nibble, and returns to the saved game. The private ARM7 tail
restores its dead hook-frame word, preserving captured WRAM bytes exactly.
Missing private acknowledgement produces L9 8140 plus the peer nibble with
ARM9 priority retained. A lost final acknowledgement holds in the secure
tail instead of entering a partly restored game.

The worker remains exactly 20480 bytes; ARM9 and ARM7 stacks remain 1024
and 384 bytes. ARM9 sector reads and ARM7 RPC transfers serially reuse the
mailbox data buffer; the separate context at offset 544 is not aliased.
The progress overlay saves exactly its 90-by-7 footprint. Live worker C uses
`-Oz`, retaining ARM7-specific code generation and interworking. The original
SDK calls have also been tested against those compiled production helpers.

The current host-verified installer places the worker at 023fa000, private
ARM7 tail at 0380c2e4, and ARM9 secure tail at 020003a0. Its local model runs
the actual save and then restore in an independent runtime with mutated RAM,
TCM, WRAM, video and CPU state; all restoration comparisons pass. Maximum
observed ARM9 stack is 872 bytes, ARM7 80 bytes. Wrong ROM/build, header CRC,
payload corruption, missing slot, early refusal and destructive read failure
are covered, together with missing private/final acknowledgement faults.
Sector callbacks are used for the full matrix; this is not a physical SD or
complete DS hardware simulation.

Old worker-build slots produce L8 1009 B before applying state. Make a new
save in P4.9 before testing load. This version check does not restrict loading
to the current boot: same-build completed files remain eligible across reboot.
Use ordinary 2D dialogue for save/advance/load, then reboot/re-enter/load.
Hardware restore, timing and repeated use still require user testing.

Reproduce the local matrix with an independently supplied private M3.2 capture:

```sh
python tests/test_rts_real_installer.py . ROM.nds --p49
python tests/test_rts_p4_arm7.py . CAPTURE.bin --p49
python tests/test_rts_p4_worker.py . CAPTURE.bin --p49 --fast-io --cache-check --bus-check
python tests/test_rts_p4_worker.py . CAPTURE.bin --p49 --reuse --fast-io --cache-check --bus-check --handoff-faults
python tests/test_rts_sound_hooks.py . CAPTURE.bin --p49
```

The first worker test writes its private fixture outside the repository;
`--reuse` requires that matching fixture. Never publish the capture, fixture,
ROM, `.sav` or disassembly with source or test packages.

## P4.8: observe direct PSG/noise timer initialization

Hardware P4.7 first shows S8 4411 B after each launch; B returns normally,
and later saves finish all 9803 sectors and return. Load shows L8 1007 B as
intended by the save-only build. The returned complete slot is phase 2,
sequence 4, with valid header/payload CRCs and the expected build/code IDs.

In that successful capture, channel 11 is inactive, format 3, with zero timer
coverage and zero shadow parameters. Other PCM channels have fff0 coverage.
Thus subsequent success did not repair channel 11 coverage: it ceased to
require a restart record once inactive.

Read-only GNU ARM disassembly of the privately supplied SDK shows the missing
paths: PSG setup at 037ff1e0 writes TMR directly from original stack[0], and
noise setup at 037ff130 writes TMR directly from original r3. Neither goes
through the previously observed timer setter. These observations explain the
missing coverage; static evidence alone does not establish exactly when that
channel stopped in the user's first refusal.

A shared original stub observes the two direct TMR stores, retaining both
SDK prologues and returns. Each replaced halfword store becomes a BL to that
stub: it saves registers/flags, masks IRQ/FIQ across shadow publication and
the displaced hardware store, then returns to the setter. This fits the
existing private patch heap, whereas two complete entry wrappers do not.
The SDK disables the channel through CNT before TMR setup, so a pre-store
interruption cannot see an already active half-programmed new channel.
PCM/timer entry observers still bracket their full calls with busy counters.
The installer validates entry patterns, timer-store and return instructions
under the exact A2GJ gate before activating any hotkey hook.
No game/SDK bytes or captured RAM are distributed.

Actual SDK tests reproduce cold active PSG11 refusal 4411 with the old two
observation points and successful preflight once it is inactive. The new
PSG hook makes its first active preflight valid (coverage 0300), without
PCM history or a prior timer modification. PSG channels 8..13 and noise 14..15
are compared with uninstrumented execution for identical MMIO writes, registers,
flags and stack, while checking that shadow publication and the timer store
are IRQ/FIQ atomic. Both produce valid restart programming.

REA raw ARM opening established artifact identity, but its Windows providers
could not analyze raw ARM. The stated function/ABI findings are ordinary GNU
objdump and local controlled instruction-model observations, not REA decompiler
Evidence. The private ledger records SHA and provider limitations.
The build stays save-only; first-attempt saving still requires hardware testing.

## P4.7: distinguish refusal sources and accept ARM7 main RAM sound aliases

P4.6 hardware showed S8 4096 B. The user powered off before trying B. The
slot is unchanged phase 0 / sequence 0; no snapshot was written. This code
was overloaded: the original private SD-busy guard can set it before ARM7
starts, and later sound/FIFO checks also used it. Thus the result alone does
not establish that the P4.6 priority fix passed on hardware.

The trace UI now maps that legacy pre-start SD-busy bit to 4010. ARM7's
preflight distinguishes sound-call busy (4101), existing FIFO error (4102)
and queue overflow (4103); ARM9 FIFO error is 4201. No FIFO guard is skipped.
The sound planner has a detailed API while preserving its original 0/1/2/3
return categories and transactional plan output: 4301..4306 identify
header/unsupported/master/bias/capture problems; 4400+channel means missing
observed fields; 4500+channel scalar range; 4600+channel sample address/span;
4700+channel unsupported PSG placement. The first failing channel is reported.

A definite range-check omission is fixed: in the gated 4 MiB DS profile,
ARM7 sound DMA can read main RAM through all four aliases in 02xxxxxx.
The previous planner accepted only 02000000..023fffff. Validation now bounds
the canonical backing span against 4 MiB while retaining the original source
address for programming. Alignment, no-wrap length, captured WRAM bounds,
field coverage and unsupported-write checks remain. This omission is not yet
confirmed as the source of the user's overloaded 4096 refusal.

The native tests cover all four main RAM aliases, exact end boundaries,
unaligned/MMIO/overflow rejection, per-channel diagnostics and unchanged plan
output on failure. Combined worker tests inject each of seven refusal sources
and require the exact S8 code, a fresh B return, no SD writes, original FIFO
contents and complete EXMEM restoration. A mirrored-source preflight is also
executed through the actual ARM9 worker. The former diagnostic data fixture
used only canonical addresses and complete sound coverage.

Mapping reference: melonDS's own [SPU DMA reads](https://github.com/melonDS-emu/melonDS/blob/master/src/SPU.cpp)
use ARM7 reads, whose [DS memory mapping](https://github.com/melonDS-emu/melonDS/blob/master/src/NDS.cpp)
uses the 4 MiB backing mask across 02xxxxxx. No emulator implementation is copied.
The build remains save-only. Physical save and B-return validation are pending.

## P4.6: borrow main RAM priority while the save server is in shared RAM

P4.5 hardware last showed S2 0044. The MMIO read has happened, but the start
store can activate ARM7 before the next trace stamp stores to main RAM. Thus
the stamp does not prove that the MMIO store itself stalled.

The independent successful M3.2 capture records EXMEMCNT=0xe880: bit 15 gives
ARM7 main RAM priority. M3.2 polls from private WRAM, while P4 moved the ARM7
server and its hot loop into main RAM. The P4 worker borrowed only Slot-1
(bit 11), leaving the now continuously fetching ARM7 at higher RAM priority.
This is a concrete arbitration-policy mismatch and a plausible cause of ARM9
starvation at the first post-start RAM access. The prior model omitted bus
arbitration, so its successful runs could not exclude this failure mode.

The save-only trace build now borrows both Slot-1 and ARM9 main RAM priority
(mask 0x8800), reads the bits back before start, and preserves the original
EXMEMCNT in the snapshot. On normal exit it sends D and waits for ARM7's zero
ACK from private WRAM BEFORE restoring the original priority. ARM7 holds in
private WRAM while peer D remains, so it cannot resume game/main-RAM execution
before ARM9 restores resources and the outer hook restores its original nibble.
A missing private ACK fails closed (8130), retaining ARM9 priority.

This change is deliberately limited to PICO_RTS_CPU_TRACE, which disables load.
The unpublished full restore needs its own final handoff/priority protocol;
simply applying this borrowing policy there would expose its early EXMEM
restore before the final CPU continuation. Do not claim read-path validation.

A conditional arbitration guard rejects ARM9 data accesses to main RAM while
the modelled main-RAM ARM7 server is active with bit 15 set. Under that explicit
hazard assumption, the preserved P4.5 binary fails at its post-start trace RAM
write and P4.6 passes save/cleanup. This is an ordering regression test, not an
emulator of all DS bus timing or proof of the unique hardware cause.
The actual ARM7 hook is tested for waiting in private WRAM through D before
resuming, as well as register/frame preservation. Missing private ACK is tested
with a visible 8130 error and retained ARM9 priority. The optional old-binary
check is in tests/test_rts_p4_priority_regression.py.

Reference for EXMEMCNT bit 15:
[BlocksDS libnds memory definitions](https://github.com/blocksds/libnds/blob/master/include/nds/memory.h).
Hardware validation is pending; the added IPC trace IDs remain available.

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
