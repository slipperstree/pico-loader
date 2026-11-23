# M1: DSPico dual-CPU rendezvous diagnostic

This is an altered research build of Pico Loader, **not an LNH-team release**.
It does **not** implement save states. There is no state file format, memory
snapshot, restore operation, or additional SD-card I/O in this diagnostic.

The current hotkey is L+R+Down+A (user request, 2026-11-23). The first hardware
report below used the earlier Select combination; the key change is covered by
instruction tests and still awaits its own hardware round.

## First hardware target

- DSPico, user's current 3DS using the 4.1.4/MSET setup, normal DS cartridge launch.
- `A2GJ`, NTR, SDK `0x03017532`: the user's Chinese AA2 ROM.
- ROM SHA256: `85e0e265a9d855a5d156a09794571b93fb13eab616814d5df49e9fcec01277fb`.
- Runtime guards check game code, SDK, the ARM7 handler signature and displaced
  epilogue instructions. They do not verify the full ROM SHA256.
- ARM9 secure-area waits at `0200018C`, `020002D6`, `020006AE`, `02000714`;
  inline CP15 wait at initial address `02006BAC`.
- ARM7 VBlank epilogue is initially at `02383C5C`.
- Other games, TWL/SDK5 and cheats are outside this first experiment.

## Build

Initialize the libtwl submodule. With Wonderful/BlocksDS configured:

```
make -j4 loader9 loader7 PICO_RTS_PROBE=1
```

The experimental ARM9 has its own filename and object directory:
`picoLoader9_DSPICO_rts_probe.bin`. Deploy it as `_pico/picoLoader9.bin`,
together with this build's `picoLoader7.bin`. Keep the current `_picoboot.nds`
and `_pico` database files. Databases are unchanged from v1.7.1 at this base.
Without `PICO_RTS_PROBE=1` the new hooks are not compiled in. Separate ARM9
object directories avoid stale feature-flag objects crossing between builds.

The research prompt uses a 4 KiB strip on the loader's DTCM stack and a local
font header. It does not use the upstream error display's `0x02100000` main-RAM
scratch buffer, because game code may already occupy that address at this stage.

## Protocol

The existing SDK ARM7 VBlank epilogue is hooked using the ABI already used by
Pico Loader's cheat engine; simultaneous cheats are therefore refused.

1. Hold L+R+Down+A for 30 ARM7 VBlanks. Both IPCSYNC nibbles and ROMCTRL
   must be idle. ARM7 publishes nibble B, then returns to the game.
2. At a patched BIOS/CP15 wait, ARM9 checks SYSTEM mode, CPU IRQ enabled,
   IME enabled, idle cartridge, ARM7 request B and its own idle nibble.
3. ARM9 saves its registers/CPSR, masks interrupts and sends ACK A. It does not
   map VRAM, access SD, transfer cartridge ownership or touch RAM mappings.
4. At a later VBlank, ARM7 sees A, masks interrupts and sends C (both CPUs
   parked). ARM9 temporarily dims both screens using MASTER_BRIGHT.
5. After 180 physical VCOUNT wraps, ARM7 releases its nibble to zero. ARM9
   restores brightness, its IPCSYNC control/output bits, IME, CPSR and registers.
   ARM7 waits for ARM9's release and restores its interrupt state and registers.

All spin loops have an instruction-count watchdog. An unanswered initial
request is withdrawn after 60 VBlank callbacks. These are bounds on software
loops, not guarantees against hardware failure. Releasing all hotkey buttons
is necessary before triggering again. Non-idle IPCSYNC is deliberately rejected.

## What is deliberately still running

DMA, timers, sound hardware and scanout are **not** suspended. In particular,
sound may loop or glitch while CPU callbacks are parked; pending IRQs can
coalesce. This diagnoses CPU rendezvous only and is not an exact hardware freeze.
It cannot demonstrate that a later state snapshot will restore correctly.

## Validation and limits

`tests/test_rts_rendezvous.py` executes the built, relocated ARM code under
Unicorn with separate CPUs and a modeled IPCSYNC register. It covers guards,
timeouts, both ARM7 entry adapters, hotkey hold/rearm, peer loss, the complete
two-CPU handshake, registers/SP/LR, control state and brightness restoration.
The bus model rejects cartridge/SD command writes. It does not simulate Nintendo
SDK dispatch, caches/MPU, real IRQ delivery, DMA, timers or audio. It also does
not execute the C++ hook installer or the generated per-call-site detours.

`tests/test_rts_patch_heap.py` compiles the actual allocator and checks optional
allocation failure does not hang or consume existing blocks, as well as best-fit,
required allocation and adjacent block merging. No new logic is exercised merely
by asserting a reimplementation of the allocator.

`tests/test_rts_probe_display.py` runs the compiled prompt and real font renderer,
rejecting all writes to game main RAM. It checks that pixels are generated,
the font asset is not modified (including an already unpacked asset), and the
function stays within its DTCM stack budget. VRAM aliases and scanout are modeled
only as writable memory; hardware display correctness remains to be tested.

Test requirements: `unicorn==2.1.4`, host C++23 compiler, ARM binutils. The ROM is
not distributed. Run the scripts from the source checkout after building.

**First hardware round passed (2026-11-23, user report).** On the user's
current 414/MSET 3DS with DSPico and the specified AA2 ROM, the user reported:
“测试了，和你预想的一模一样，没问题。” (Tested; behavior matched the
expectation, with no problems observed.) This confirms the expected M1
pause/continue path for that setup. Trial count, exact duration, CPU state and
long-session stability were not instrumented or independently measured. Other
ROMs/consoles and actual save-state restoration remain unvalidated.

## Further work after hardware rendezvous passes

Capture/restore CPU banked state, DTCM/ITCM, game RAM, ARM7/shared WRAM and caches;
coordinate DMA/timers and cartridge/file state; preserve video and audio state,
including write-only/hidden hardware state; then implement validated and atomic
state-file serialization. A RAM dump or a copied `.sav` is not a save state.

No public save-state PR has been opened for this diagnostic.

## Sources and attribution

- [LNH-team/pico-loader](https://github.com/LNH-team/pico-loader), base
  `b9f923e`, zlib license. Existing VBlank signature/epilogue approach comes from
  its cheat engine. The original license is retained.
- [VideoGameMore/Pico Loader PR 228](https://github.com/LNH-team/pico-loader/pull/228):
  BIOS wait detours and inline CP15 hook installation are adapted from that work,
  with attribution. This experiment does not import its return/reload pipeline.
- [Patt92 experimental nds-bootstrap RTS](https://github.com/Patt92/nds-bootstrap/tree/feature/experimental-rts)
  was read as an architectural reference only. No GPL code has been copied.
- [GBATEK](https://problemkaputt.de/gbatek.htm) for the hardware register model.
