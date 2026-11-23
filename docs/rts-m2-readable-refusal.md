# M2.3: keep refusal reasons visible until acknowledgement

## M2.2 hardware result

The same 414/MSET 3DS now responds to L+R+Down+A: the user observed a line
of text, paused audio/video, then normal play after about two seconds. They
could not read the line. Read-only inspection found the expected M2.2 Loader,
but the snapshot is byte-for-byte unchanged from initialization: phase 0,
sequence 0, zero CRC fields and entirely zero payload. Triggering and returning
are observed; a successful capture is not. The best match is an S8 refusal,
but the reason cannot be inferred from timing alone. The file is preallocated
at startup; its existence does not mean the hotkey wrote a snapshot.

## Change

Where VRAM is safe, `M2 S8 0002 B` now remains visible until the user releases
B and presses it afresh. The numeric reason is unchanged from M2.2. A B held
on entry cannot dismiss the line. Heartbeats alternate once per physical
frame throughout this deliberate pause, keeping ARM7's existing watchdog
alive. Per-frame waiting is bounded if VCOUNT stops. No filesystem/card I/O
is added to a refusal, and the same display state is restored after B.

Active DMA/capture retains M2.2's three brightness flashes and automatic
return, with no VRAM remapping. No capture guard is relaxed and no card-bus
ownership is changed. The protocol, capture format and write/readback/commit ordering are unchanged.
The header readback sector buffer is reused, explicitly cleared, for excluded
workspace sectors during payload writes; the separate 512-byte zero buffer is
removed to retain the exact 8 KiB reservation with the added diagnostic code.
Full-capture tests verify zero exclusion and end-to-end CRC after this change.

The compiled-worker model checks acknowledgement after four seconds, B
already held on entry, heartbeats during waiting, exact display/register
restoration, and no SD command for owner/mapping/DMA/capture refusals.
Progress glyph bounds, actual patch installation and rendezvous checks are
also run against the new binaries. This remains capture research without
a restore path; M2.3 hardware result is pending.
