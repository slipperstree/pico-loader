# P6 experimental in-game save/load menu

P6 integrates the four-slot controller and renderer from stage 1 into the
existing save-state worker. This is an opt-in DSPico DS-mode build, pending
physical-console testing. It does not add a game whitelist or a mandatory
payload verification pass.

## Controls and files

Hold **L+R+A** for approximately half a second, then release the buttons. The
menu pauses both CPUs, mutes master output, and uses a black lower screen with
four white slot frames. Left/right traverse all four slots with wrap-around;
up/down change rows. A opens actions, then confirms the highlighted action.
Occupied slots default to green Load; empty slots show only green Save.
Left/right do nothing in the action menu. B backs out, then returns to the game.
Save/load completion returns automatically.

For `Example.nds`, launch preparation allocates:

| File | Purpose |
| --- | --- |
| `Example.rts` | Slot 1, preserving the original filename convention |
| `Example.rts2` | Slot 2 |
| `Example.rts3` | Slot 3 |
| `Example.rts4` | Slot 4 |
| `Example.rts-menu` | Preview/time metadata, menu image and temporary VRAM backup |

All files remain beside the ROM; UTF-8 paths use the existing FatFs support.
Each slot keeps the P4/P5 payload format and per-ROM identity. Creating all
four files reserves roughly 20 MB per game and adds work to its first launch.
Existing files are not truncated. A foreign file, wrong size, insufficient
space or excessive fragmentation disables installation rather than replacing
the conflicting file. Preexisting P5 snapshots have a different code/build
identity and must be recreated in P6 before they can be loaded.

Thumbnails are 80x60 RGB555 samples of the **main graphics engine**. This can
represent either physical screen. Capture chooses bank C or D when it is not
needed as a main-engine BG/OBJ/texture source; when neither can be borrowed,
the state still works with a black preview. The last complete capture is
associated with the slot's snapshot sequence. Missing metadata displays an
unknown time (`----/--/--`, `--:--:--`) and does not display stale preview bytes.
RTC time is sampled on save through the parked ARM7 server, without writing
the clock; 12-hour mode is converted to 24-hour display.

`/_pico/rts-debug.txt` defaults to `on`. Set it to `off` or `0` to hide the
successful-install prompt and progress diagnostics. The progress bar and
percentage remain visible. Errors still show a code and a B acknowledgement
where returning to the current game is safe. Existing save/load verification
settings remain independent; load remains a single payload pass by default.

## Resident worker and transient overlay

The all-in-RAM prototype exceeded the tested SDK arena. The integrated design
keeps the resident arena at **20 KiB**, the same reservation as P5.0. The menu,
font, slot maps and its division helpers execute temporarily in VRAM bank H.
The boot preparer stores the checked overlay image and RAM relocation offsets
in the auxiliary file. The resident core backs up H before installing that
image, relocates references to the allocated worker, and restores H only after
returning to resident code. Calls into a partially restored overlay are gated
off. Byte-written controller state remains in RAM because DS VRAM does not
support byte stores; overlay data is read-only or uses halfword/word writes.

Banks C and D are preserved before display capture and menu drawing. Save
streams the original C/D/H bytes from the auxiliary backup into the snapshot.
Load defers C/H writes into that backup, keeping the menu and its executable
overlay intact until the last display handoff. The final restoration uses
separate staging storage so it does not overwrite the ARM9 CPU-state buffer.
ARM7 master mute/unmute and RTC reads use three new commands in the existing
parked server; music playback position remains subject to the earlier sound
restart limitations.

## Build

```sh
make -j4 loader9 loader7 \
  PICO_RTS_SNAPSHOT=1 PICO_RTS_ARM7_CAPTURE=1 \
  PICO_RTS_VIDEO_CAPTURE=1 PICO_RTS_RESTORE_PROBE=1 \
  PICO_RTS_LIVE_RESTORE=1 PICO_RTS_MENU=1
```

Install `picoLoader7_menu_p6.bin` and `picoLoader9_DSPICO_menu_p6.bin` as the
usual `/_pico/picoLoader7.bin` and `/_pico/picoLoader9.bin`. Keep the existing
Chinese-capable launcher boot file. Omitting `PICO_RTS_MENU=1` selects the
earlier direct-hotkey build; P5's tagged checkpoint remains the rollback source.

## Verification and limits

- Native C controller/renderer tests: release gating, cyclic navigation,
  occupied/empty defaults, timestamps, percentages, diagnostics and pixel bounds.
- Real FatFs in an isolated image: all four Chinese-named slots, disjoint sector
  maps, existing payload preservation, debug configuration and foreign-aux rejection.
- Real installer on the private A2GJ test ROM: the 20 KiB arena fits, five pause
  hooks and seven sound-store hooks install, boot data relocates, LRA is patched.
- ARM7 execution tests: GPIO RTC reads in 12/24-hour modes, original pin state
  restoration, invalid time handling and the actual mute/clock/unmute server loop.
- Integrated worker model: four slots, changed-scene/cross-boot restoration,
  menu cancellation, complete original/target VRAM preservation, audio master
  restoration and a guard against byte stores to VRAM. It checks all RAM/TCM,
  general/CP15 registers and ARM7/ARM9 continuation, not just the header.

The fast integration mode supplies sector callbacks and may use host CRC and
skip repeated busy pixel redraws; native rendering and earlier full-CRC runs
exercise those implementations separately. A full SD-command cancellation run
checks the menu backup/restore path without the sector shortcuts. These models
do not emulate DS display capture, physical SD timings or real LCD brightness.
Console screenshots, pause latency and graphics/audio behavior still require
the user's 414 3DS test. Existing internal-3D and game compatibility limitations
remain unchanged.
