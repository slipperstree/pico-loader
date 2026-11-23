# M3: restore research, starting from the validated CPU continuation

## Stable baseline

M2.6 FAST on the user's current 414/MSET 3DS/A2GJ target returned normally.
The actual file passed desktop CRC: phase 2, sequence 3, CRC 8E0B6AC9,
655 physical write frames (about 10.92 s at nominal 60 Hz). SHA256:
429da936698bf9fca6ad1ca9de557a2c0ae36a671e7cd3674e6dc030ef781bcf.
A private copy is retained outside source and public artifacts. G: remains on
M2.6; this branch deliberately does not enable a restore hotkey yet.

## Implemented first primitive

`RtsBuildArm9Continuation` validates the captured gate/worker frames and
identifies the actual post-gate caller stub. It requires an externally verified
payload, checks memory/stack/workspace bounds, System-mode gate state, saved
register agreement, known ARM/Thumb stub instructions and the ARM WFI detour's
return branch. It publishes the 68-byte continuation only after all checks pass.
It accepts diagnostic M2 data for **CPU-context analysis only**; it does not
authorize an overall game-state load or replace full-file compatibility checks.

The actual capture uses a main-RAM stack at 020A6F30, not DTCM. The captured
`regs[15]` points back into the worker-entry machinery; `regs[14]` is the caller
continuation. Confusing these would jump into the wrong return sequence. The
current gate frame is 48 bytes, preceded by the 56-byte worker entry frame;
both are cross-checked against payload bytes protected by the verified CRC.

`rtsEnterArm9Continuation` is a stackless ARM946 primitive. From a privileged
masked context it uses IRQ mode to load System SP/LR, then atomically returns
registers, PC and CPSR using LDM exception return. It preserves IRQ SP/LR and
uses SPSR_IRQ as the exception-return latch; it is **not** a complete banked-CPU
state restore. A final integrated loader must also restore the relevant banked
state and all memory/hardware preconditions. The helper must live in a region
that remains executable when final MPU permissions are restored (for example,
the trusted secure-area patch heap), not blindly in the protected work area.

The new C and assembly files are intentionally absent from the live M2 build
rules. No game memory or device file is modified by this research module.

## Verification

`tests/test_rts_arm9_continuation.py REPO [PRIVATE_SNAPSHOT]` compiles the C
validator natively and for ARM946, and executes the actual ARM return primitive
under Unicorn. Synthetic ARM WFI and Thumb BIOS-wait cases restore registers,
CPSR/Thumb state, stacks and IRQ SP/LR, and execute the matching original caller
epilogues. Guest memory writes are rejected. BIOS wait/WFI completion is modeled,
not physical interrupt delivery. Incomplete/unverified captures, corrupt frames,
unsupported modes, invalid stack/return ranges, modified stubs and reader errors
must not publish even a partial context. The user's real M2.6 capture also passes
and reaches its original caller continuation in this model. No private capture
bytes are committed or shipped in the source artifact.

Architecture references: [ARMv5 architecture manual](https://documentation-service.arm.com/static/5f8dacc8f86e16515cdb865a),
[Arm LDM/STM semantics](https://support.arm.com/documentation/dui0489/e/arm-and-thumb-instructions/memory-access-instructions/ldm-and-stm?lang=en).
The banked-register LDM interlock is explicitly included. No external emulator
or save-state implementation code is copied.

## Remaining work before a real load

1. Capture/restore ARM7 private 64 KiB and shared 32 KiB WRAM, its interrupted
   CPU context, banked registers and IRQ return state. ARM9 cannot simply read
   private ARM7 WRAM; it needs an ARM7-side staging protocol that preserves the
   paused frame and keeps both CPUs on controlled stacks during restore.
2. Capture VRAM, palettes, OAM, relevant display/3D state, IRQ/timer/IPC state,
   and sound state. A raw MMIO dump is insufficient for write-only, write-one-
   to-clear or hidden device state; unsupported states need explicit limits.
3. Define an extended M3 checkpoint with section bounds/CRCs, exact ROM/build/
   session identity and compatibility policy. M2 files remain diagnostic and
   cannot be upgraded into full checkpoints merely by changing their flags.
4. Validate the entire input before modifying game memory. Restore from a
   protected workspace, retain ownership/error guards, and only release CPUs
   after memory, hardware and both continuations are coherent.
5. First hardware load target stays the same 414 machine and AA2 dialog scene.
   A future candidate load chord is L+R+Down+B; it is not wired up in this build.

The next hardware-testable checkpoint version must capture the extra state
first, so it will require a new save. Keeping M2.6 working while developing
the missing pieces avoids presenting this CPU primitive as a working load.
