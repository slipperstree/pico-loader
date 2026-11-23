# M2.4: borrow Slot-1 only after whole-transaction guards

## Hardware evidence

On M2.3, the same 414/MSET 3DS/A2GJ test displayed `M2 S8 0002 B`.
That is the EXMEMCNT bit-11 refusal before any SD command. The Loader's own
startup sets `REG_EXMEMCNT |= 0x8880`, routing Slot-1 to ARM7. Ownership by
ARM7 is therefore a normal condition, not evidence of a failed cartridge.
The previous capture code expected ARM9 to already own it. The card was initially absent. After reconnection to G:, the expected M2.3
Loader was confirmed and the capture was byte-for-byte unchanged from its
initialized phase-0/sequence-0, zero-payload file; a local copy was retained.

## Guarded handoff

Do not simply remove the ownership guard. A clear CARD busy bit does not
prove an entire DSPico SD transaction is idle: E3/E4/E5 or F6/E4 exchanges
have idle gaps between commands. The snapshot build's actual synchronous SD
read/write entry points now set a busy word before calling their original
bodies, and clear it only on complete return. Arguments, r4, stack alignment
and return ABI are preserved. Each relocated instance has its own busy word.
The ARM7 installer checks both ARM7-instance addresses before enabling RTS.
Default and M1 builds do not contain these wrappers.

At the ARM7 park boundary, a busy read or write yields reason 4096. The owning
ARM7 interface is also checked for CARD ROM busy and SPI busy; existing DMA
and sound-capture guards remain. This covers commands that became busy after
the original hotkey request. The reason is published before the parked ACK.

After both CPUs park and all guards pass, ARM9 saves EXMEMCNT, clears only
bit 11, and reads it back before touching the cartridge. A failed acquisition
keeps S8 reason 2 and performs no SD command. Original EXMEMCNT is included
in header reserved word 1. On successful CRC/commit, ARM9 restores its card
registers and original EXMEMCNT before releasing ARM7. Ownership restore
failure is fail-closed S9 code 9, before closing the diagnostic display. SD errors still hold both CPUs rather than
resuming an uncertain transaction. Other EXMEM bits and Slot-2 are preserved.

This is target-specific capture research, not a complete save-state restore.
ARM7/GPU/audio state remains incomplete. DMA/capture and active transactions
are declined; banked CPU state and hidden device state are not restored.

## Verification

The real installer executes on a separately supplied hash-checked A2GJ ROM,
checking all wait hooks and ARM7 code/guard literal allocation. Actual Thumb
wrapper tests verify full-call busy lifetime and argument/stack/r4 preservation.
The actual ARM7 rendezvous tests inject read/write busy flags and owning-side
ROM/SPI activity; each must publish refusal and return both CPUs safely.
The actual relocated worker completes a full write/readback CRC starting with
ARM7 ownership and restores it exactly. A second relocation starts with ARM9
ownership. The model rejects SD commands without ARM9 ownership and parked
ARM7, and all writes must stay inside mapped capture sectors. Failed ownership
writes, unsupported TCM, invalid mapping and active transactions are refused
without SD I/O. Prompt/glyph bounds and nonresearch compilation are checked.
Physical bus timing, cache/MPU details and actual card firmware remain for the
next hardware round; M2.4 is not marked hardware-passed.

## Emulator testing boundary

Unicorn tests here execute compiled ARM code against explicit IPC/card/SD
models; they are not a complete NDS emulator. A full NDS emulator can test
game execution and peripheral interactions more broadly, but directly opening
the retail ROM does not exercise the patched loader plus DSPico storage path.
It needs an appropriate cartridge model or a test storage backend. The
emulator's own host-side savestate function is not the in-game RTS code.
This work currently runs on the DS CPUs and uses DSPico's extended SD protocol.
Another cartridge would require a storage/protocol integration, not merely
copying the resulting Loader binary.

Sources inspected (2026-11-23):
- https://github.com/LNH-team/dspico-firmware
- https://github.com/melonDS-emu/melonDS/blob/master/src/NDSCart.cpp

The inspected melonDS cartridge construction dispatch covers retail, homebrew
and R4 models, without a DSPico branch there. That source observation is not a
claim about every emulator or third-party fork. No GPL emulator code is copied.
