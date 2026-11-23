# Restore-side ARM7 primitives (unlinked research)

M3.2 hardware capture and normal return passed on the same 414/MSET 3DS/A2GJ
target: CRC DCF52708, 1076 write frames, about 17.93 seconds. No new firmware
is deployed for this milestone; G: remains on the known working M3.2 capture.

## Actual restore code

`RtsValidateArm7Continuation` requires a verified payload, known context ABI,
aligned/in-range workspace and saved frame, exact frame/payload agreement and
consistent active bank SP/LR. The first supported continuation is IRQ mode with
IRQ masking set and ARM state, matching the observed VBlank epilogue. It does
not authorize restoring an entire diagnostic checkpoint. System-mode returns
remain rejected because their unmasked interrupt-release window needs a
different integrated design.

The real capture returns to 037FB948, a shared-WRAM mirror, not the canonical
03000000 aperture. Bounds validation handles the full ARM7 shared/private
mirror ranges without permitting a transfer to wrap across the physical bank.
The model mirrors canonical shared writes into the actual high return aperture.
Unused bank SP/LR/SPSR can contain uninitialized values; the primitive restores
these raw captured banks without dereferencing their stacks.

`rtsArm7RestoreSector` runs stacklessly from main RAM and copies one validated
512-byte stage into ARM7 private/shared WRAM. Before writing it checks the
block bound, masked IRQ/FIQ, privileged supported mode, IME=0, aligned main-RAM
source, main-RAM return address and (for shared blocks) WRAM allocation 3.
It never calls the BIOS, game hooks or a function in WRAM being overwritten.
Future integration must place caller/helper in protected workspace, preserve
its source/context and validate the entire file and session before any write.

`rtsEnterArm7Continuation` restores six banked SP/LR sets, exception SPSRs and
FIQ r8-r12 without using a game stack. It then switches to the validated IRQ
context, advances SP past the original hook's saved frame, restores IME/CPSR,
loads saved r2-r12/LR and reaches the original VBlank caller. r0/r1 remain
caller-scratch according to the original epilogue ABI. It is not a generic
arbitrary-PC CPU restore routine. The underlying IRQ SPSR remains intact.

ARM9 continuation analysis now accepts exact M2/M3.1/M3.2 header layouts and
still requires the verified payload and matching code/stack frames. The test
uses the correct fixed ITCM section instead of assuming ITCM is the last file
section. This lets both CPU return primitives be tested with the same real
M3.2 capture without forging its version or format.

## Verification

`tests/test_rts_arm7_restore.py REPO [PRIVATE_M32_CAPTURE]` builds the ARM7TDMI
assembly and native/ARM validator, fills modeled private/shared WRAM with bad
bytes, clobbers every bank and general registers, and executes all 192 real
sector writes plus the actual return primitive. The synthetic IRQ fixture and
the private hardware capture both restore exact WRAM bytes, six banks, FIQ
registers, active SP/CPSR and reach the saved IRQ caller. Every memory write is
restricted to the expected destination sector; the return may write only IME.
Invalid bounds, source, IME, IRQ mask, return location and shared allocation
make no writes. Unverified/invalid contexts are rejected before execution.

`tests/test_rts_arm9_continuation.py` passes with the real M3.2 capture as well.
It checks the original ARM9 return stub and CPU state, modeling completion of
the original WFI/BIOS wait. Neither test emulates a complete Nintendo system,
actual pending interrupts, synchronized CPU release, graphics or sound.
Neither test executes a full continued game after the restored caller.

## Material remaining blockers

The observed DISPCNT_A is 00011D18: normal display mode, 3D selected for BG0 and
BG0 enabled. This is evidence that a 2D-only recovery assumption is unsuitable;
it does not prove nonempty polygons at the exact capture instant. VRAM capture
alone does not establish geometry/render-state recovery. Shadowing/replay or a
target-specific reinitialization path needs further investigation.

ARM9 banked/CP15 state, write-only display state, audio, IRQ/timers/IPC/hidden
device state, exact ROM/build/session identity, complete preflight and safe
two-CPU release remain incomplete. `tools/inspect_rts_restore.py` validates file
integrity then reports these blockers. All current diagnostic formats remain
unconditionally unauthorized for live loading, even with valid CRC and CPU
continuations. No load chord or call site is connected to the game build.

Reference for DISPCNT interpretation and ARM7 memory mirrors:
[GBATEK](https://mgba-emu.github.io/gbatek/). All new restore code is original.
