# M2.5: optional full readback, faster CRC, retained I-cache and frame timing

## Hardware baseline

M2.4 completed S5 and S6 and returned normally on the user's 414/MSET 3DS
with the supplied A2GJ image. Read-only inspection of the actual TF file
passed: phase 2, sequence 1, payload CRC D9808E0F, 4,243,968 bytes, workspace
023FA000+2000, DTCM 027C0000. File SHA256 is
5ecb27173dbe47e7eebc5b4102731ffe5008a56efc967a2d643631467cdc0ecf.
The capture is preserved privately outside the repository and release package.
The user corrected the elapsed-time estimate to **over three minutes**.
This is a successful diagnostic capture, not a working restore/save-state feature.

## Readback switch

`/_pico/rts-verify.txt` is read when launching the game. `fast` skips the full
S6 payload readback; `full` retains it. Missing, unreadable or unknown settings
fall back to full. CRLF and an optional UTF-8 BOM are accepted. The config
travels through the existing 288-byte loader message; its boot-only mode bit
is removed from the runtime refusal word. Startup clearly displays FAST/FULL.
The supplied TF overlay explicitly selects `fast` for this performance round.
Restart the game after changing the file; it is not a live toggle.

Both modes compute the payload CRC while writing and still acknowledge every
sector, commit the completion header and read back that header exactly. Fast
mode flags=3 and verifyCrc=0 explicitly mean **no in-console full readback**.
Full mode retains flags=1 and equal payload/readback CRCs. Version and layout
remain compatible with old full captures. The updated desktop checker always
computes CRC over the actual file, including fast captures, and rejects a
fast header that pretends to contain a full-readback CRC. Future loading must
validate stored data before applying it; loading is not implemented here.

In the immediately-ready device model, total commands fall from 41,450 to
16,586. Real hardware may poll readiness more often; these are model counts,
not a measured device speedup. No DSPico firmware/protocol change is required.

## CPU-side changes

The old word-wise CRC performed 32 bit steps per word. A 64-byte nibble table
performs eight nibble steps with identical reflected CRC32 results. Executing
the actual old/new compiled CRC functions on a 512-byte sector takes 29,316
versus 5,765 ARM instructions (80.3% fewer) and matches zlib on zero, FF and
seeded data. Instruction counts do not model bus/cache timing or total latency.

The previous `control & ~5` also disabled the MPU, which makes all instruction
fetches noncacheable on ARM946E-S even with the I-cache enable bit set. The new
path retains the MPU, ensures main-region I-cache eligibility, and disables
only D-cache and write-buffer attributes after flushing game data. It restores
the original control, instruction-cache eligibility and buffer attributes on
success, with I-cache invalidation around attribute changes. The existing
secure-area region-2 guard remains. The exact SDK mapping already permits
main RAM, MMIO/VRAM, DTCM and the 01FF8000 ITCM data alias. The model checks
actual read addresses against that SDK MPU layout and requires retained MPU/
I-cache plus disabled D-cache/buffering for every card command. Physical cache
coherence and timing remain for hardware validation.

Reference: [ARM946E-S TRM, sections 3.2 and 4.1](https://documentation-service.arm.com/static/5e8e3ee588295d1e18d3aa82).

## Timing and footprint

ARM7 counts physical VCOUNT wraps while parked, publishing one aligned 32-bit
word in a dedicated 32-byte shared line. ARM9 does not modify that line, and
reads it while D-cache is off. Existing game timers and audio state are not
borrowed for profiling. The line is disjoint from mutable worker/header data.
Reserved header word 4 is PFT1 (31544650); words 5/6 contain payload-write and
readback frame deltas; word 7 covers first header access through payload work.
This excludes initial rendezvous/cache preparation and final header commit/
display restoration. The checker reports raw frames and approximate seconds
at nominal 60 Hz. Fast mode's readback duration remains zero. No real M2.5
duration has been measured yet.

The calculated reservation increases by 512 bytes to 8,704 bytes, ending at
023FC200 for the supplied ROM. The existing arena reservation logic advances
by that exact generated size before launching the game. Tests impose an
explicit 9 KiB ceiling, validate arena/stack boundaries and zero exclusion;
the old fixed-8-KiB test bound is intentionally superseded, not silently dropped.

## Validation

- Actual FatFs config parsing, closed physical map, existing payload preservation,
  fragmentation and foreign-file protection.
- Real installers for fast and full startup/config flags, five wait hooks,
  ARM7 guard pointers and a dedicated aligned clock line.
- Actual ARM7 counter matches physical wraps, resets on repeated captures,
  and preserves the existing CPU/IPC/MPU guard invariants.
- Actual relocated worker full capture/readback at two bases, no-SD refusal
  and bounded transport/CRC faults; fast captures omit S6 and retain payload CRC.
- Deliberately corrupt fast writes commit without claiming a readback, and are
  rejected by the desktop CRC checker. Fast mode cannot detect such damage at
  capture time; this is the explicit verification/performance tradeoff.
- Prompt isolation, saved progress strip boundaries, CRC instruction comparison
  and research-off compilation. M2.5 hardware result remains pending.
