#pragma once
#include "RtsArm9CpuState.h"
#include "RtsArm9Continuation.h"
typedef struct {
    RtsArm9Continuation continuation;
    uint32_t region2,control;
} RtsArm9RestoreTail;
#ifdef __cplusplus
static_assert(sizeof(RtsArm9RestoreTail)==76);
extern "C" {
#else
_Static_assert(sizeof(RtsArm9RestoreTail)==76,"restore tail ABI");
#endif
// Unlinked research. Requires validated target mapping, D-cache OFF, restored
// memory/TCM, target lockdown=0, and stable context in the dead saved game frame.
// Tail code must be in trusted secure-area RAM, outside protected region 2.
void rtsRestoreArm9State(const RtsArm9CpuState*,const RtsArm9RestoreTail*,void* tailCode);
void rtsArm9RestoreTail(const RtsArm9RestoreTail*);
#ifdef __cplusplus
}
#endif
