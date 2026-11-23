# M3.1: ARM7-assisted diagnostic capture

This is an altered Pico Loader research build for the single A2GJ / SDK
03017532 target on the user's 414/MSET 3DS. It is not a loadable save state.
The working M2.6 capture is retained as the hardware-validated baseline.

## Implemented and integrated

The ARM7 VBlank hook captures its parked frame, CPSR/IME, six mode banks
(System, IRQ, SVC, abort, undefined, FIQ) and FIQ r8-r12 into a 512-byte
context before publishing the parked IPC acknowledgment. It then services
bounded 512-byte copy requests from ARM9 while polling the existing VCOUNT
clock/heartbeat loop. Helpers run from the already reserved main-RAM workspace
and never push to the game stack or modify private/shared WRAM. The hook's
existing saved frame remains in game RAM and is copied consistently.

The current-bank LR captured after a helper call would be instrumentation's
return address. The context substitutes that bank's pre-call LR from the
parked hook frame. The temporary helper return/CPSR fields are cleared before
publishing the context magic. A restore implementation must reconstruct the
hook epilogue contract, not treat these as arbitrary interrupted game r0-r15.

The first capture target supports ARM7 System/IRQ modes and WRAM allocation 3
(all 32 KiB shared WRAM assigned to ARM7). Other allocations/modes decline with
S8 8192 and allow a fresh B acknowledgment. No mapping changes are attempted;
reading an unmapped shared range could otherwise capture private-WRAM mirrors.

ARM9 operates with D-cache/write buffering off during payload transfer, as in
M2.6. The mailbox is aligned to 32 bytes, separate from the ARM7 frame-clock
line. ARM9 publishes block/request before command, then waits for completion;
ARM7 publishes data/status before the matching completion number. ARM9 keeps
the existing heartbeat and physical-frame deadline while waiting. Duplicate
requests do not execute again; block bounds and WRAM allocation are checked.

## File and build isolation

Build: `make -j4 loader9 loader7 PICO_RTS_SNAPSHOT=1 PICO_RTS_ARM7_CAPTURE=1`

Outputs use `_capture_m3` names and `build/rts-worker-m3`, distinct from M2.
The new file is `/_pico/RTS-A2GJ-M3.bin`; M2 is not resized or overwritten.
Magic 31435452, version 00030001, 4342784 total bytes (8482 sectors).
Payload: 8481 sectors. Header ABI is retained but the new version is incompatible.

| File offset | Bytes | Contents |
| --- | ---: | --- |
| 000000 | 512 | Header, completion marker, whole-payload CRC, ARM9 capsule |
| 000200 | 4194304 | Main RAM, with reserved workspace zeroed |
| 400200 | 16384 | DTCM |
| 404200 | 32768 | ITCM |
| 40C200 | 512 | ARM7 parked/banked context |
| 40C400 | 65536 | ARM7 private WRAM |
| 41C400 | 32768 | ARM7 shared WRAM |

The workspace grows from 8704 to 10752 bytes, still guarded by the real
allocator. The actual target installer fits five ARM9 wait hooks and the
840-byte ARM7 hook without displacing mandatory SD patches. No extra large
RAM buffer is required: ARM7 stages one sector in the 1056-byte mailbox.

The existing fast/full setting and real CRC remain. New channel errors fit
the four-digit display: 8008 = ARM7 completion deadline; 8007 = frame clock
stalled; 8021 = invalid block; 8022 = changed WRAM allocation; 8025 = missing
ARM7 context. As with M2.6, S9 holds both CPUs; B is for S8 only.

## Validation and remaining work

- ARM7TDMI helper execution in System/IRQ: exact six banked contexts and FIQ
  registers, all 192 exact memory blocks, duplicate/bounds/mapping guards,
  unchanged game memory/stacks. Unsupported allocations 0/1/2 decline.
- Actual ARM7 hook + actual ARM9 wait hooks: repeated dual-CPU rendezvous,
  heartbeat/clock, normal return and existing refusal/timeout regressions.
- Actual worker + actual ARM7 copy helper + modeled sector device: full and
  fast file capture, exact section bytes/CRC, alternate relocation, incompatible
  file preservation, invalid map/mode refusal before issuing SD commands.
- Real A2GJ installer execution validates arena/patch allocation and literals;
  actual FatFs preparer validates creation, exact size, fragmented allocation
  and incompatible-file preservation on an isolated image.
- Desktop checker validates CRC, section metadata and agreement between ARM7
  context frame and captured stack; rejects corruption even with recomputed CRC
  when the copied frame disagrees. CRC detects errors; it is not authentication.

These are model tests, not Nintendo hardware, physical cache-coherence, sound
or graphics restoration tests. M3.1 requires its own hardware capture round.
It deliberately has no load hotkey and never overwrites game RAM from a file.
Missing state still includes ARM9 banked/CP15 details, VRAM/palettes/OAM,
display/3D state, sound and IRQ/timer/IPC/device state, plus a complete-file
preflight/identity policy and safe two-CPU restore ordering.

Hardware memory-map reference: [GBATEK WRAM allocation](https://mgba-emu.github.io/gbatek/).
No external emulator or save-state implementation code is copied.
