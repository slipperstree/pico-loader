# M2.6: physical deadlines after the I-cache speedup

## Hardware evidence and limits

On M2.5 FAST the user observed much faster S5 progress, followed by S9 0004
and a white diagnostic screen. They estimate the count was near 8288 but do
not recall it exactly. B did not respond, as designed for a fail-closed S9.
After power-off and reconnecting G:, both Loader hashes matched M2.5. The
file is incomplete: phase 1, sequence 2, flags 3, CRC/timing fields zero.
SHA256: 320032507b1b6600b345002e19a5fad65dd95d86b0ed0c766831604785aa7581.
The failed file is retained privately; the first successful M2.4 capture is
also retained. This does not establish an exact failing sector or substep.
Runtime errors are not written to a failing SD transport just to log them.

S9 0004 was the generic payload-write failure. The previous code used a
4096-response ceiling plus a shared CPU-loop budget. An actual compiled M2.5
sector-function regression demonstrates that it rejects a device returning
ready after 5000 polls, although its modeled elapsed time is below 180 frames.
I-cache and CRC changes expose a definite dependence on polling/CPU speed.
That is a reproduced logic defect, not proof it is the sole hardware cause.

## Change

Each read/write sector transaction starts one 180-physical-frame deadline,
including its data transfer and readiness polling. No word or command resets
that deadline. ARM7's existing independent scanline counter supplies time.
Readiness succeeds immediately when observed; no fixed per-sector sleep or
loss of FAST mode, CRC optimization or I-cache improvement is introduced.

While waiting, ARM9 continues heartbeat changes when the frame advances,
keeping the parked ARM7 watchdog alive. A separate finite spin fallback is
reset only when the independent clock advances; it catches a stopped clock
without replacing normal elapsed-time deadlines. Timeouts do not resend an
uncertain write, commit a completion header, or release either CPU.

The protocol's E4 status command reports completion asynchronously; see
[official command documentation](https://github.com/LNH-team/dspico-firmware/blob/472c9d8e9957ad18df367f14b9cc337b9b887e65/docs/commands.md)
and [SD command implementation](https://github.com/LNH-team/dspico-firmware/blob/472c9d8e9957ad18df367f14b9cc337b9b887e65/src/ntrCardRomGameSd.cpp).
Only protocol behavior was inspected; no firmware code is copied or flashed.

## Error display

S9 now shows `M2 S9 4006/8273`: error code / logical file sector at the last
transaction, where sector 0 is the header. For I/O failures the code is the
original phase category times 1000 plus the wait detail:

| Detail | Meaning |
| --- | --- |
| 1 | File-sector mapping failed |
| 2 | Payload data FIFO did not become ready |
| 3 | Payload/initial command busy did not clear |
| 4 | Status command response did not become ready |
| 5 | Status command busy did not clear after its response |
| 6 | SD kept returning not-ready until the deadline |
| 7 | Independent frame clock stopped advancing |

For example, 4006 means payload write / SD not ready, while 1004 means initial
header read / status-response wait. Non-I/O errors (foreign header, CRC mismatch,
failed ownership restoration) retain their old small codes. The suffix is the
current or most recent I/O sector, not the /8288 progress total. S8 still waits
for B; S9 deliberately does not resume. Power off before removing the TF card.

## Validation

`test_rts_transport_waits.py REPO [OLD_ELF]` executes the actual sector routines:
the old ELF reproduces rejection at 4096; the new one accepts 5000-poll delays.
At two modeled CPU poll rates, the same readiness frame succeeds and an
unready device stops at frame 180. Data FIFO, command-end, status-response,
status-end, perpetual not-ready and stopped-clock cases are bounded; heartbeat
changes continue, and uncertain writes are not resent. Full-worker tests execute
the real error body through S9 rendering and the fault IPC signal, so assertions
observe the displayed composite code rather than its earlier function argument.
Progress glyph tests check the failing-sector suffix within the saved strip.
Existing full/fast CRC, readback, relocated captures, mode flags, RAM/stack bounds
and guard refusals are retained. The generated reservation remains 8704 bytes.

M2.6 hardware success is pending. The binary still captures diagnostic memory
only; complete game-state restore/load is not implemented.
