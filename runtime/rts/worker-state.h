#pragma once
#include <stdint.h>
#include "RtsSnapshotInfo.h"
typedef struct {
    RtsSnapshotInfo info;
    uint32_t base,bytes;
    RtsM2Header header;
    uint32_t readback[128];
    uint16_t videoBackup[96*8];
    uint32_t oldDisplay;
    uint16_t oldBrightness;
    uint8_t oldVramC,videoActive;
} WorkerState;
extern WorkerState gRtsM2;
extern volatile uint32_t gRtsM2Frames[8];
