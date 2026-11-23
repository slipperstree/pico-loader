# M2.2: held-key retry and observable refusals

## Hardware observation

On the same 414/MSET 3DS and A2GJ image, the user saw the normal
`RTS research: snapshot M2.1` startup message, but two hotkey attempts had no
visible effect. The card still contained the expected M2.1 Loader hashes and
the snapshot remained initialized (phase 0, sequence 0, zero payload).
This does not prove which runtime guard rejected the request.

The optional `tests/test_rts_real_installer.py REPO ROM` executes the built
Loader's actual ARM9 and ARM7 patchers, TLSF allocator and fragmented patch
heap in Unicorn, with separately supplied game data. It confirms all five wait
hooks, the actual `02006BAC` WFI patch, the ARM7 callback, the enabled flag,
the `023FA000` worker and its diagnostic literal. Thus the earlier suggestion
that a fragmented heap silently skipped installation is not supported.
Cache maintenance and screen prompt calls are modeled or bypassed here;
this test cannot validate hardware MPU/cache coherence or card timing.

## Changes

The ARM7 hotkey handler previously latched a press as fired *before* checking
card busy and IPC idle. If either check failed on the threshold frame, it
discarded the entire press until release. It now latches only when publishing
a request, so holding L+R+Down+A retries temporary busy conditions.

ARM7 DMA and sound-capture refusals now reach the parked ARM9 worker through
the reserved configuration word. ARM9 invalidates that read-only shared cache
line before reading it. No refusal issues an SD command. A one-shot ARM9 DMA
or display capture is given two physical frame wraps to settle before checks
are repeated. Persistent DMA/capture is still refused; no guard is relaxed.

When VRAM is safe, refusal shows `S8` and a decimal reason mask for roughly
three seconds, then restores the original display. With active DMA/capture,
both screens flash three times using brightness registers only: VRAM mapping
and framebuffer pixels remain untouched. Frame waits have a per-wrap finite
software budget if VCOUNT stops. Reasons are bit masks and may be combined:

| Value | Condition |
| --- | --- |
| 1 | Unsupported TCM layout |
| 2 | Card bus owned by ARM7 |
| 4 | Card ROM transfer busy |
| 8 | Card SPI busy |
| 16/32/64/128 | ARM9 DMA channel 0/1/2/3 enabled |
| 256 | Invalid allocated snapshot mapping |
| 512 | ARM7 DMA enabled |
| 1024 | ARM7 sound capture enabled |
| 2048 | Display capture enabled |

The MPU entry guard now carries original region 2 in wrapper-preserved r12,
avoiding an extra two-word stack frame. Snapshot frame offsets and the saved
region capsule match that layout. The worker still reserves exactly 8 KiB.
M2.1's two-word frame/120-byte entry description is historical; M2.2's entry
is 112 bytes. The M1 rollback also receives the held-key retry fix.

## Validation and limits

The actual compiled rendezvous tests cover retries after busy, ARM7 refusal
delivery and both CPU returns, MPU guard mutation rejection, and preserved
registers. Actual relocated worker tests cover full writes/readback CRC at
two addresses, bounded SD errors, no-SD refusals, three flashes with no VRAM
remap, S8 duration/display restoration, and one-shot DMA completion before
the first SD command. Prompt isolation and progress pixel bounds remain
covered. The real installer integration test uses a hash-checked, external
ROM; no ROM or extracted SDK bytes are distributed.

The user's next hardware round must establish whether requests now arrive
and, if refused, which feedback appears. M2.2 has not passed that round.
This remains a diagnostic memory capture, without complete ARM7/GPU/audio
state or a restore path, and is not advertised as working save/load states.
