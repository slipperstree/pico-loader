# DSPico save-state development checkpoint

This branch preserves the complete local development history through **P5.0**.
The code checkpoint is `ba75af0f150e017adeee6c30af915afe4a05eb15`; later documentation-only commits do not
change the installed runtime. This is an opt-in development branch.

## Repository relationship

Pico Launcher and Pico Loader are separate Git repositories. Chinese filename
rendering is a launcher change; in-game save/restore is a loader change.
Their commit histories are preserved separately rather than combined through
an unrelated-history merge.

- Loader feature branch: [slipperstree/pico-loader, feature/dspico-savestates](https://github.com/slipperstree/pico-loader/tree/feature/dspico-savestates).
- Chinese display-fix branch: [slipperstree/pico-launcher, fix/utf8-icon-labels-and-filename-fonts](https://github.com/slipperstree/pico-launcher/tree/fix/utf8-icon-labels-and-filename-fonts).
- Launcher and loader development remain independent. A temporary launcher
  save-state branch contained documentation only and has been removed; no
  launcher save-state branch is needed.
- Launcher feature-branch base: the existing UTF-8 display-fix commit
  [`0665b36`](https://github.com/slipperstree/pico-launcher/commit/0665b36498f74b4109a1780fc33359bea34c6602).
- The locally tested launcher with the selectively integrated Chinese font
  assets is `5328510a5fcde4a9254aab22df5d90bb60a51dd5`, preserved as
  `chinese-paths-tested-2026-11-24` in the launcher fork. This is distinct
  from the smaller UTF-8-fix contribution branch.

## Named rollback points

| Ref in this repository | Code baseline | Evidence |
| --- | --- | --- |
| `rts-p5.0-2026-11-24` | P5.0, code `ba75af0` | Multi-game recognition and muted restore passed local integration/model tests; new-game hardware validation pending. |
| `rts-p4.10-verified` | P4.10, `04ca8af` | User confirmed save, restore, and gameplay restoration from the title screen after restarting the tested A2GJ game on a 414/MSET 3DS. |

The preceding research commits remain in the branch history, including the
pause, snapshot, cache/IPC arbitration, first-save, and persistent-restore
milestones. The original local research branches are retained too.

## Current behavior

- Save: **L+R+Down+A**. Load: **L+R+Down+B**.
- One `.rts` slot beside each ROM, using the ROM's basename and actual game ID.
- Completed checkpoints can survive restarting the game or power cycling.
- Default load reads/applies the payload once (`L2`). Set
  `/_pico/rts-load-verify.txt` to `full` for the optional `L1` CRC pass;
  `fast` or a missing file leaves it disabled.
- The game-title/exact-SDK whitelist is removed. Actual wait/VBlank code,
  private patch space, and a reserved 20 KiB worker determine eligibility.
- Common SDK sound stores are recognized dynamically, including ARM7 autoload
  address translation. Missing sound metadata may use a muted restart plan
  instead of refusing save/load. Audio may return after the game fully sets up
  and starts new music; recovery on every scene change is not guaranteed.
- Pause discovery, memory layout, active DMA/capture, internal 3D state,
  write-only display state, and exact timer phase remain separate limitations.

Build changes can move resident hooks. Recreate checkpoints after incompatible
build changes; the build-identity check prevents resuming through stale addresses.
The existing ordinary `.sav` is not rolled back by an in-memory checkpoint.

## Build the experimental loader

Use the normal Wonderful/BlocksDS prerequisites and the pinned `libtwl`
submodule. The local checkpoint used `arm-none-eabi-gcc` 16.2.0.
From a clean checkout/build directory:

```sh
git clone --recurse-submodules --branch feature/dspico-savestates https://github.com/slipperstree/pico-loader.git
cd pico-loader
make -j4 loader9 loader7 \
  PICO_RTS_SNAPSHOT=1 PICO_RTS_ARM7_CAPTURE=1 \
  PICO_RTS_VIDEO_CAPTURE=1 PICO_RTS_RESTORE_PROBE=1 \
  PICO_RTS_LIVE_RESTORE=1
```

The internal build suffix remains `p49`; the displayed/runtime distribution
version is P5.0. Install `picoLoader7_restore_p49.bin` as
`/_pico/picoLoader7.bin` and `picoLoader9_DSPICO_restore_p49.bin` as
`/_pico/picoLoader9.bin`. Building without these flags produces the ordinary
loader, not this save-state experiment. The launcher boot file is separate.

To return to the hardware-confirmed code baseline:

```sh
git fetch origin --tags
git switch --detach rts-p4.10-verified
make clean
# Rebuild with the same experimental flags shown above.
```

Keep local changes on a branch before switching checkpoints. Return to
`feature/dspico-savestates` to continue current development.

## Validation recorded for P5.0

- Full worker save/restore in an independent runtime, including mutated
  RAM/TCM/WRAM/video, CPU state, default single-pass load, and opt-in CRC.
- Non-A2GJ slot identity and save/restore with unsupported sound muted.
- Actual ARM7 RPC/return flow and missing private/final handoff acknowledgements.
- Real FatFs per-game slot isolation and independent load/save verification options.
- 1,344 original-versus-patched store/register/flags/MMIO cases across six
  private ROM inputs, plus muted-plan and active sound-capture guard tests.
- Eight of eleven representative installer inputs completed; two failed in
  the baseline ARM9 patch/model stage and one lacked an RTS work area.
- The sound recognizer matched 184 of 196 files in the private local sample.
  This is recognition coverage, not a hardware compatibility percentage.

The actual code and detailed experiments are documented in
[rts-p4-experiment.md](rts-p4-experiment.md). Test ROMs, RAM snapshots, ordinary
save files, private disassembly, access tokens, generated binaries, and local
TF-card packages are not included in the pushed source history.
