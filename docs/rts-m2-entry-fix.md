# M2.1: safe entry into the SDK-protected work area

## Hardware failure and source evidence

The user reported that M2 dimmed the screens and stayed frozen for five minutes.
The G: card's two Loader hashes matched the M2 release. Read-only inspection of
`RTS-A2GJ-M2.bin` found the original initialized header (phase=0, sequence=0) and
an entirely zero payload. This proves no first capture write completed; it does
not, by itself, distinguish entry failure from an initial read/transfer stall.
The original capture has been retained locally for investigation.

The exact A2GJ ARM9 SDK image supplies the missing hardware condition:

- Initial instruction AP register at `02000B48` is `05100011`; data AP at
  `02000B4C` is `15111011`. Region 2's AP nibble is zero in both.
- The ordinary 4MiB path at `02005AE8..02005AF4` calls the region setters with
  `0200002B` (region 1) and `023E0021` (region 2, constant at `02005B0C`).
- Region 2 covers `023E0000..023FFFFF`, including the M2 worker at `023FA000`.
  Jumping into it before removing protection can fault before any worker C code
  or SD access. The previous model intentionally did not emulate MPU mappings
  and therefore missed this defect. The observed failure is consistent with it;
  the fix's actual hardware success still needs to be tested.

## Fix

The trusted secure-area ARM9 stub now saves CP15 region 2, temporarily disables
that region, calls the worker, and restores the exact original region afterward.
The game thread remains in the existing masked-interrupt rendezvous throughout.
Disabling region 2 exposes region 1's ordinary main-RAM permissions for the
worker. Original protection is restored only after the wrapper has switched back
to the game's DTCM stack. The added two-word guard frame is reflected in the
register capsule and the original region is saved in header reserved word 0.
No attempt is made to restore a complete game state in this stage.

The split dim/entry fragment remains 120 bytes, fitting the existing fragmented
patch heap. The complete worker now reserves 8KiB; it uses the same bounded ARM7
arena reservation, ending at `023FC000` for this ROM and retaining main-heap space.

## Progress and timeout diagnostics

The worker temporarily displays bank C as the main framebuffer and changes just
a 96x8 pixel strip. Its original pixels, VRAM C mapping, main display control and
brightness are saved and restored on successful return. The rest of the temporary
framebuffer is existing VRAM content and is not a UI artifact to judge.

The strip displays `M2 S5 0128/8288`: S1 entry, S2 cache maintenance, S3 header read,
S4 invalidation header write, S5 payload writes, S6 readback, S7 completion, or S9
error with an error code. The normal payload progresses in blocks of 64 sectors.
Active display capture is rejected in addition to DMA/sound capture. Error paths
keep the diagnostic line visible and require reboot, preserving the existing
fail-closed policy. SD-ready retries now share an overall per-sector polling
budget and a reduced finite command retry limit.

## Verification

- The real ARM7/ARM9 rendezvous regression now starts with the SDK's protected
  region and a worker at the actual protected address. Entry is rejected unless
  the guard has opened it. Removing the opening MCR instruction makes the test
  reject entry; normal runs require the original region restored exactly.
- The actual relocated worker, including progress rendering, completes full
  captures and readback CRC at two addresses, with actual SDK DTCM base `027C0000`
  in the model. Full VRAM and relevant display registers must equal their initial
  values after success, and main RAM is still protected outside the workspace.
- A separate real-code progress test rejects all framebuffer writes outside the
  saved 96x8 strip and checks rendered pixels for S1/S3/S5/S6/S9. Existing invalid
  mapping, DMA, foreign header, readback corruption and transport timeout tests pass.
- Loader startup prompts remain isolated from game RAM. All checks remain models
  of hardware behavior; real SD timing, MPU/cache details and return-to-game need
  the user's next hardware round.

Original sources/licenses and the M1/M2 attribution remain unchanged. The SDK
disassembly used for diagnosis is not distributed in the patch or test package.
Hardware reference: [ARM946E-S Technical Reference Manual](https://documentation-service.arm.com/static/5e8e3ee588295d1e18d3aa82).
