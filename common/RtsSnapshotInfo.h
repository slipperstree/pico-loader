#pragma once
#include <stdint.h>

// M2 is a diagnostic capture, not a restorable save-state format.
#define RTS_M2_MAGIC 0x324D5452u
#define RTS_M2_VERSION 0x00020001u
#define RTS_M2_GAME 0x4A473241u
#define RTS_M2_PAYLOAD_BYTES (0x400000u + 0x4000u + 0x8000u)
#define RTS_M2_FILE_BYTES (512u + RTS_M2_PAYLOAD_BYTES)
#define RTS_M2_FILE_SECTORS (RTS_M2_FILE_BYTES / 512u)
#define RTS_M2_MAX_EXTENTS 32u
#define RTS_M2_CONFIG_FULL_VERIFY 0x80000000u
#define RTS_M2_VERIFY_PATH "/_pico/rts-verify.txt"
#define RTS_M2_FLAG_DIAGNOSTIC 1u
#define RTS_M2_FLAG_NO_READBACK 2u
#define RTS_M2_TIMING_MAGIC 0x31544650u // PFT1: physical frame timing
#define RTS_M2_FILE_PATH "/_pico/RTS-A2GJ-M2.bin"
typedef struct { uint32_t count, sector; } RtsM2Extent;
typedef struct {
    uint32_t magic, version, fileSectors, extentCount;
    uint32_t dataStart, dataEnd, gameCode, reserved;
    RtsM2Extent extents[RTS_M2_MAX_EXTENTS];
} RtsSnapshotInfo;

typedef struct {
    uint32_t magic, version, fileBytes, gameCode;
    uint32_t phase, payloadBytes, payloadCrc, sequence;
    uint32_t workspaceBase, workspaceBytes, dtcmBase, dtcmBytes;
    uint32_t itcmBase, itcmBytes, control, dtcmConfig;
    uint32_t itcmConfig, verifyCrc, error, flags;
    uint32_t regs[16];
    uint32_t gateCpsr, frameAddress;
    uint32_t reserved[90];
} RtsM2Header;
#ifdef __cplusplus
static_assert(sizeof(RtsSnapshotInfo) == 288);
static_assert(sizeof(RtsM2Header) == 512);
#else
_Static_assert(sizeof(RtsSnapshotInfo) == 288, "M2 file map size");
_Static_assert(sizeof(RtsM2Header) == 512, "M2 header size");
#endif
