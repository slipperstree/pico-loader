# M2: DSPico diagnostic memory capture

This is an altered research build based on Pico Loader. M1's initial hardware
test passed on the user's 414/MSET 3DS and A2GJ ROM on 2026-11-23. **M2.4 full capture and M2.6 fast capture have now passed hardware
return-to-game and desktop payload CRC checks.** M2.6 sequence 3 recorded
655 write frames (about 10.92 seconds), CRC `8E0B6AC9`. This stage captures memory; it does not implement game
state loading, and its files must not be presented as usable save states.

The requested hotkey is now **L + R + Down + A** (`0x381`). The old Select
combination no longer triggers. The included M1 fallback uses the same new key.


The first M2 hardware attempt froze before any capture write completed. M2.1
fixes an SDK MPU entry defect and adds visible progress; see
[rts-m2-entry-fix.md](rts-m2-entry-fix.md). The initial M2.1 hardware failure is historical; current M2.6 behavior is
documented in [rts-m2-timeouts.md](rts-m2-timeouts.md).

## Capture path

- Still restricted to DSPico, NTR A2GJ, SDK `0x03017532`, cheats off.
- Before loading the game, ARM7 uses the project's FatFs to create/validate
  `/_pico/RTS-A2GJ-M2.bin` (4,243,968 bytes), sync/close it, and publish up to 32
  extents clipped to exactly the file's sectors. A foreign/incompatible file is
  rejected. An existing compatible capture is retained until a new capture.
- No FAT or directory updates happen in game. The runtime can address only the
  validated preallocated file sectors. It checks bounds, lengths and overlap.
- The ARM9 worker is compiled as a self-contained ARM image. The packer rejects
  external calls and unexpected relocations; only validated internal ABS32
  locations are rebased. The generated image/header lives in `build/rts-worker`.
- The current M2.6 runtime reserves 8,704 bytes of main RAM. It is reserved
  through ARM7's arena, aligned to 512 bytes, and bounded below `0x023FF000`.
  On the exact ROM, the existing main arena literal is `0x027F9C08`; after the
  existing 512-byte save buffer, this maps to a workspace at `0x023FA000`.
- A separate 1 KiB worker stack keeps the game's DTCM stable during capture.
  Main RAM is streamed sector by sector; the worker's reserved region is stored
  as zeroes and explicitly described in the header.
- ARM7 rejects active DMA/sound capture. ARM9 rejects active DMA, busy card/SPI, and unsupported TCM layouts.
  Whole ARM7 SD transactions and owning-side card/SPI are checked before parking.
  ARM9 temporarily borrows Slot-1 after both CPUs park and restores ownership
  before returning to the game.
- ARM9 records the M1 frame/register capsule, CP15 configuration, 4 MiB main
  RAM, 16 KiB DTCM and 32 KiB ITCM. It cleans the D-cache using the existing
  ARM946 cache-maintenance sequence and keeps the MPU/I-cache available while disabling D-cache and write buffering
  during capture. Original control and attribute settings return on success.
- Phase 1 invalidates completion before payload writes. The worker writes the
  payload and stores its CRC32. Full mode reads it back and compares CRCs; fast
  mode skips that pass and explicitly records flags=3, verifyCrc=0. Phase 2
  commits the header, which is read back exactly before returning to the game.
- A/9 IPCSYNC heartbeats keep ARM7 parked beyond M1's old three-second duration;
  D marks completion. Sector I/O has a 180-physical-frame deadline, with a finite stopped-clock
  fallback and continued heartbeats while waiting. Transport/CRC errors
  signal E and fail closed with white screens: the user must reboot rather than
  resume save callbacks while cartridge state might be unknown. Loss of the
  worker heartbeat also holds ARM7. A precheck rejection resumes without SD I/O.

## What this does not capture yet

ARM7 private/shared WRAM and full banked CPU contexts, video/VRAM, audio/timer
state and hidden/write-only hardware state are not serialized. The register
capsule describes the rendezvous trampoline, not a generic exception frame.
DMA and sound capture are rejected rather than frozen/restored. Timers, sound
playback and scanout continue, and may glitch while game callbacks are parked.
No memory is restored to the game. Flags=1 (full) or flags=3 (fast) declare the file diagnostic-only.

## Build and tests

```
git submodule update --init --recursive
make -j4 loader9 loader7 PICO_RTS_SNAPSHOT=1
```

Deploy `picoLoader7_snapshot_m2.bin` as `_pico/picoLoader7.bin` and
`picoLoader9_DSPICO_snapshot_m2.bin` as `_pico/picoLoader9.bin`. Keep the Chinese
launcher and database files. ARM7/ARM9 M2 objects and outputs are separate from
M1/default builds. Plain `PICO_RTS_PROBE=1` builds the new-hotkey M1 fallback.

Validation before hardware:

- `test_rts_snapshot_worker.py` executes the real relocated worker and actual SD
  command loops against an in-memory DSPico protocol model. Full captures and
  readback CRC pass at two relocation bases. Invalid maps, active DMA, foreign
  headers, corrupted readback and transport timeout are checked. The model rejects
  any write outside the allocated file and writes to game RAM outside the small
  workspace. Stack writes must remain in the worker's own stack. CP15 operations
  are recorded/modelled, not physical cache/MPU/TCM emulation.
- `test_rts_snapshot_prepare.py` builds the real preparer with the project's
  real FatFs against an isolated FAT32 image. It checks exact length, closed file
  map, direct last-sector access, existing payload preservation, foreign-file
  protection, fragmented chains and excessive fragmentation rejection.
- `test_rts_rendezvous.py --m2` exercises real ARM7/ARM9 handshake code with a
  model worker to check heartbeats beyond 180 physical wraps, repeated cycles,
  DMA/capture prechecks, and fail-closed heartbeat loss. The new combination is
  checked and the old Select combination is rejected. Plain mode checks M1.
- `tools/check_rts_snapshot.py` checks length, completion phase, CRC, layout and
  the excluded workspace without writing to disk or the console.

Tests require Unicorn 2.1.4, host C/C++ compilers and ARM binutils. The test
drivers write only under `build/`. No ROM or snapshot is included in source.
Actual SD timing, supported idle states, ARM946 cache/mapping behavior and game
recovery must still be established on the user's hardware.

No save-state feature PR has been submitted. Attribution and original license
remain as documented for M1; SD commands follow the existing DSPico platform
driver. No nds-bootstrap code is copied.
