# Restore foundations: ARM9 state, file preflight and restartable sound

These components were first validated independently. They are now integrated
in the opt-in [P4 experiment](rts-p4-experiment.md). Existing M2/M3 files remain
diagnostic captures and are not accepted as loadable P4 checkpoints. P4 has
passed local execution models; physical save/load testing is still pending.

## ARM9 control state and final handoff

`rtsCaptureArm9Cpu` records six SP/LR/SPSR banks, FIQ r8-r12 and 19 CP15 values
in a 512-byte record. It is stackless, changes no CP15 configuration and
preserves the calling mode/flags. System SP/LR are replaced with the saved game
continuation values; MPU region 2 is replaced with its pre-guard value, because
the existing safe stub has already opened that region before entering workers.

`rtsRestoreArm9State` restores cacheability, bufferability, permissions, MPU/TCM,
lockdown and trace-ID settings plus banked state while keeping region 2 open
and D-cache disabled. The final tail must execute from trusted secure-area RAM
and read its 76-byte context outside the region being closed. It closes region
2, restores the final control value and atomically resumes the caller with an
exception return. The test puts the context in the now-dead captured stack
frame, below the resumed SP. Future integration must validate that placement
and mappings before overwriting any memory.

The inactive IRQ SPSR is used as the exception-return latch for the System-mode
ARM9 caller, so that one raw inactive SPSR is not preserved. It is overwritten
on the next hardware IRQ. This is a target-specific continuation mechanism,
not an arbitrary all-register CPU save/restore API. Physical cache contents and
locked-cache restoration are not tested; the intended target requires no
locked cache ways. Raw restore primitives have no live callers yet.

`test_rts_arm9_state.py` executes the actual capture/restore code for ARM and
Thumb callers. It clobbers banks and modeled CP15 state, verifies all 19 values
and active registers after return, and rejects the regression where a context
is still in protected workspace when region 2 closes. The real M3.2 continuation
also passes with **synthetic supplemental CPU state**, since M3.2 did not capture
those extra banks/CP15 values. These tests model CP15/cache effects rather than
claiming physical cache coherence or a continued game.

## Whole-file preflight and identity comparison

`RtsInspectCheckpoint` introduces a separate experimental manifest with header,
section and payload CRCs plus caller-supplied ROM/build/session SHA/ID fields.
It checks exact file size, phase, known flags, section geometry, bounds,
contiguity, duplicates and all contents before publishing a result. It has only
a sector-read callback; there is no memory-write callback. On any error the
caller's output remains untouched. Even successful inspection always sets
`allowRestore=0`, because current manifests are diagnostic and per-device
semantics/restore integration remain incomplete.

This compares supplied identity values; it does **not** yet compute a live ROM
hash, create a boot/session identity, write a manifest, or connect to loader I/O.
The caller will need trusted expected identity, not values merely copied from
the file being checked. Successful CRC proves error detection, not authenticity.

`test_rts_checkpoint_preflight.py` tests a full synthetic memory/display manifest
natively and executes the ARM946 binary with a sector reader. Wrong ROM/build/
session, truncation, malformed sections, corruption and last-sector read failure
are rejected without publishing partial output. Descriptive capabilities alone
cannot turn a diagnostic file into an authorized load.

## Sound restart, as accepted by the user

The first experiment may restart current music/effects instead of recovering
the internal sample-play position. `RtsObserveSoundWrite` records byte/halfword/
word writes with per-byte coverage. Restart planning rejects active channels
whose source/timer/loop/length were not captured, invalid sample ranges,
unsupported PSG channels or active capture units. It publishes a 512-byte plan
only after all active channels pass. Preparation mutes/stops channels and
programs parameters; release starts them later, after memory/device coherence.
Neither operation is connected to live MMIO in the game yet.

Local analysis of the private M3.2 ARM7 image identified the PCM setter at
037FF298 and timer setter at 037FF068. Their programming semantics were then
executed in Unicorn for all 16 channels; they are not assumed from a symbol name.
Optional stubs record their original arguments, replay displaced instructions
and preserve ABI/flags. An IRQ-protected nesting count stays nonzero until the
original SDK function exits, so capture can refuse an incomplete hardware update.

`test_rts_sound_restart.py` validates coverage/range guards and restart ordering.
`test_rts_sound_hooks.py` compares actual private SDK code with compiled hooks:
all 16 channels have identical MMIO writes, registers, flags and stack returns,
including timer changes. Parameters from those calls produce a valid restart
plan. This is programming-level verification, not sound playback/streaming QA.
Runtime hook discovery/installation and ARM7-side live control readback still
need integration. No private binary/snapshot bytes are included in source.

The local literal/store scan found geometry-writing candidates too. They are
candidate observations, not proof that geometry state is recoverable. Graphics
shadowing/replay, timer/IRQ/IPC handling, final coordination and a testable live
loader remain unfinished.

Register reference: [ARM946E-S TRM](https://documentation-service.arm.com/static/5e8e3ee588295d1e18d3aa82).
All new implementation code is original; no external save-state code is copied.
