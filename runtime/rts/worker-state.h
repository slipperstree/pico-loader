#pragma once
#include <stdint.h>
#include "RtsSnapshotInfo.h"
#include "RtsVideoCapture.h"
typedef struct {
    RtsSnapshotInfo info;
    uint32_t base,bytes;
    RtsM2Header header;
#ifdef PICO_RTS_LIVE_RESTORE
    // ARM9 sector reads and ARM7 RPC data transfers are strictly serial.
    // Mailbox context at +544 remains independent from this shared buffer.
    uint32_t* readback;
#else
    uint32_t readback[128];
#endif
    #ifndef PICO_RTS_MENU
    uint16_t videoBackup[RTS_PROGRESS_WIDTH*RTS_PROGRESS_HEIGHT];
    #endif
    uint32_t oldDisplay;
    uint16_t oldBrightness;
    uint8_t oldVramC,videoActive;
} WorkerState;
extern WorkerState gRtsM2;
extern volatile uint32_t gRtsM2Frames[8];
