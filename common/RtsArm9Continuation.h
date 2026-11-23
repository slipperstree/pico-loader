#pragma once
#include <stdint.h>
#include <stddef.h>
#include "RtsSnapshotInfo.h"

// M3 research primitive only. Validating a CPU continuation does not make an
// M2 diagnostic capture restorable. No live Loader call site exists yet.
typedef struct {
    uint32_t cpsr, systemSp, systemLr;
    uint32_t frame[14]; // r0-r12, PC, for IRQ-mode LDM exception return.
} RtsArm9Continuation;
typedef int (*RtsReadCapturedBytes)(void* user,uint32_t address,void* out,uint32_t bytes);
enum RtsContinuationResult {
    RTS_CONTINUATION_OK=0, RTS_CONTINUATION_UNVERIFIED=1,
    RTS_CONTINUATION_HEADER=2, RTS_CONTINUATION_MODE=3,
    RTS_CONTINUATION_RANGE=4, RTS_CONTINUATION_FRAME=5,
    RTS_CONTINUATION_STUB=6, RTS_CONTINUATION_READ=7
};
#ifdef __cplusplus
extern "C" {
#endif
#ifdef _WIN32
__declspec(dllexport)
#endif
int RtsBuildArm9Continuation(const RtsM2Header* header,int payloadVerified,
    RtsReadCapturedBytes read,void* user,RtsArm9Continuation* out);
// Unlinked from the game build until ARM7/memory/peripheral restore exists.
void rtsEnterArm9Continuation(const RtsArm9Continuation* context);
#ifdef __cplusplus
}
static_assert(sizeof(RtsArm9Continuation)==68);
static_assert(offsetof(RtsArm9Continuation,frame)==12);
#else
_Static_assert(sizeof(RtsArm9Continuation)==68,"continuation ABI");
_Static_assert(offsetof(RtsArm9Continuation,frame)==12,"continuation frame ABI");
#endif
