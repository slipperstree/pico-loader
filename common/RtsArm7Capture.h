#pragma once
#include <stdint.h>
#include <stddef.h>
#define RTS_ARM7_CONTEXT_MAGIC 0x31433741u // A7C1, diagnostic parked continuation
#define RTS_ARM7_BLOCKS 192u
typedef struct {
    uint32_t magic, version, parkSp, parkCpsr, ime, wramMode, reserved[2];
    uint32_t frame[12]; // Saved r2-r12/LR at the VBlank-hook epilogue.
    uint32_t banks[6][3]; // System, IRQ, SVC, abort, undefined, FIQ: SP/LR/SPSR.
    uint32_t fiqR8R12[5];
    uint32_t padding[85];
} RtsArm7Context;
typedef struct {
    volatile uint32_t command, request, completed, status, block, reserved[3];
    uint32_t data[128];
    RtsArm7Context context;
} RtsArm7Mailbox;
#ifdef __cplusplus
static_assert(sizeof(RtsArm7Context)==512);
static_assert(sizeof(RtsArm7Mailbox)==1056);
static_assert(offsetof(RtsArm7Context,banks)==80);
#else
_Static_assert(sizeof(RtsArm7Context)==512,"ARM7 context ABI");
_Static_assert(sizeof(RtsArm7Mailbox)==1056,"ARM7 mailbox ABI");
_Static_assert(offsetof(RtsArm7Context,banks)==80,"ARM7 banks ABI");
#endif
