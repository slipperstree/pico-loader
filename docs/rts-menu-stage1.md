# Four-slot save/load menu: stage 1

This checkpoint adds an isolated, freestanding C controller and RGB555 renderer.
It is **not linked into the live loader**. Building and installing the current
loader still produces the P5.0 behavior: one `.rts` file per ROM, save with
L+R+Down+A and load with L+R+Down+B. No on-card files need replacing for stage 1.

The user reports that P5.0 save/restore worked in several games. The game names
and exact checkpoints were not recorded, so this is a limited field report,
not a claim of general compatibility.

## Implemented and tested in isolation

- The future menu trigger is L+R+A (`0x0301`, active-high DS key bits).
  Releasing all three keys is required before A can confirm a menu action.
- A black 256x192 lower-screen framebuffer has the title `S/L Menu` and four
  white 82x62 frames arranged in two rows. A green outline marks selection.
- Occupied slots accept streamed 80x60 RGB555 thumbnails through a callback.
  The renderer centers `yyyy/mm/dd` and `hh:mm:ss` below each frame. Empty slots
  show `Empty` without timestamps.
- Right/left advance or retreat through indices 0, 1, 2, 3 with wrap-around.
  Up/down change rows while preserving the column. Held directions repeat;
  held A never confirms a second time.
- A opens Save/Load to the upper right of the selected frame. Occupied slots
  default to green Load; empty slots show only green Save. Up/down change the
  action; left/right are ignored. A returns the selected operation to the caller.
- B returns from actions to slot selection, then from slot selection to the game.
  Input is ignored while the caller is applying a save/load operation.
- Busy frames show Saving/Loading, a progress bar, and integer percentage.
  Diagnostic text is optional. The controller explicitly transitions to closed
  when the caller reports successful completion.
- A parser for the future `/_pico/rts-debug.txt` setting defaults to enabled.
  `off` and `0` disable it; whitespace, UTF-8 BOM and case are handled.
  This parser is not yet wired to the live startup/debug screens.

`RtsMenu` uses 60 bytes. There is no heap allocation, filesystem access or MMIO in
these modules. The caller owns the framebuffer (98,304 bytes) and thumbnail I/O.
The test thumbnail callback supplies synthetic blocks and example timestamps;
these are not real game captures or persisted save-state metadata.

## Validation

```sh
python tests/test_rts_menu.py . --storyboard --arm
```

Requires a native C compiler (`CC`) and, for `--arm`, an ARM toolchain
(`ARM_NONE_EABI_PREFIX`). Windows Wonderful DLLs are resolved from
`WONDERFUL_TOOLCHAIN/bin`. Native tests cover key-release gating, wrap-around,
operation defaults, repeat behavior, timestamps, debug parsing, percentage
overflow/zero boundaries, framebuffer canaries and debug-independent progress.
`--storyboard` emits all 16 occupancy combinations with every selection/action.
`--arm` compiles for ARM946E-S with warnings as errors and links with `libgcc`
without libc or unresolved symbols. This is a module-level link test, not a
complete firmware or emulator test.

On Wonderful GCC 16.2.0 with `-Os -marm`, the isolated ARM9 ELF contains 3,958
bytes of text/rodata, no data/bss, and needs a caller-provided state/framebuffer.
The largest individual compiler-reported C frame is 80 bytes; this is not a
whole-call-tree stack bound or a live-worker fit guarantee.

## Hardware integration still required

1. Back up and restore the full lower-screen VRAM used by the menu. The existing
   20 KiB worker is nearly full and only backs up the old progress-strip pixels.
   Adding the renderer to that worker without a separate storage plan is not
   sufficient.
2. Capture the **main graphics engine** before replacing its display state. This
   may correspond to either physical screen, depending on the game; the user
   chose this scope for the first implementation. Downsample into the thumbnail.
3. Pause both CPUs through the existing rendezvous; dim the physical upper
   screen and mute audio while the menu is open; restore the game on B or success.
4. Preallocate/map four per-ROM slots at launch, select the proper raw block map,
   and store each slot's screenshot/time metadata. Preserve the existing basename
   convention and offer the old single `.rts` as slot 1 if migration is feasible.
   No slot filename or on-disk metadata format is finalized by this checkpoint.
5. Read the real RTC, stream existing thumbnails, and distinguish missing slots
   from invalid/incompatible states with suitable messages.
6. Wire debug configuration into startup diagnostics and progress updates, and
   replace the old direct save/load hotkeys with the menu entry point.
7. Test menu cancellation, first save, overwrite, all four slots, ordinary load,
   restart/title-screen load and display/audio restoration on the user's 414 3DS.

A separate VRAM overlay with a preallocated scratch file is under investigation
for the renderer and full-screen preservation. Its bank selection, restore
ordering and performance require hardware testing before installation. Stage 1
does not change existing snapshot formats, worker hooks or loader binaries.
