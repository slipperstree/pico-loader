#pragma once
#include <stdint.h>
#include <stddef.h>
#define RTS_ARM9_CPU_MAGIC 0x31503941u // A9P1
typedef struct {
    uint32_t magic,version,entryCpsr,reserved;
    uint32_t banks[6][3]; // System, IRQ, SVC, abort, undefined, FIQ SP/LR/SPSR.
    uint32_t fiqR8R12[5];
    // control, D-cache regions, I-cache regions, buffer regions, D/I extended
    // AP, MPU regions 0-7, DTCM/ITCM, D/I lockdown, trace process ID.
    uint32_t cp15[19];
    uint32_t padding[82];
} RtsArm9CpuState;
#ifdef __cplusplus
static_assert(sizeof(RtsArm9CpuState)==512);
static_assert(offsetof(RtsArm9CpuState,cp15)==108);
extern "C" {
#else
_Static_assert(sizeof(RtsArm9CpuState)==512,"CPU state ABI");
_Static_assert(offsetof(RtsArm9CpuState,cp15)==108,"CPU CP15 ABI");
#endif
// Unlinked research. Call with IRQ/FIQ masked in System mode before changing
// cache/MPU state. Caller zeroes the struct. Override worker SP/LR and already
// opened MPU region 2 with the original saved game values.
void rtsCaptureArm9Cpu(RtsArm9CpuState*,uint32_t gameSp,uint32_t gameLr,uint32_t originalRegion2);
#ifdef __cplusplus
}
#endif
