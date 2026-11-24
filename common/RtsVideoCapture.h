#pragma once
#include <stdint.h>
#define RTS_VIDEO_MAGIC 0x31434456u // VDC1, diagnostic display metadata.
#define RTS_VIDEO_VRAM_BYTES 0xa4000u
#define RTS_VIDEO_SECTION_BYTES 0xa5200u
typedef struct {
    uint32_t magic,version,vramBytes,paletteBytes,oamBytes;
    uint32_t display[2],brightness[2],vram[9],power,wram,bgControl[8];
    uint32_t reserved[100];
} RtsVideoCapture;
#ifdef __cplusplus
static_assert(sizeof(RtsVideoCapture)==512);
extern "C" {
#else
_Static_assert(sizeof(RtsVideoCapture)==512,"display metadata ABI");
#endif
// Returns 0 for unsupported C/D ownership. No mapping or RAM writes.
int RtsPrepareVideoCapture(RtsVideoCapture*,uint32_t brightnessMain,uint32_t brightnessSub);
// One sector after metadata: VRAM A-I, standard palettes, OAM. Changes only
// one bank's mapping temporarily, restoring its live mapping before return.
int RtsReadVideoSector(const RtsVideoCapture*,uint32_t sector,uint16_t out[256],const uint16_t* progressBackup);
#ifdef __cplusplus
}
#endif


// The live loader uses exactly the 15-character, 5x7 progress footprint.
// Diagnostic CPU tracing retains its original padded strip.
#ifdef PICO_RTS_LIVE_RESTORE
#define RTS_PROGRESS_WIDTH 90u
#define RTS_PROGRESS_HEIGHT 7u
#else
#define RTS_PROGRESS_WIDTH 96u
#define RTS_PROGRESS_HEIGHT 8u
#endif
