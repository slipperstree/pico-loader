#pragma once
#include <stdint.h>
#include "RtsSnapshotInfo.h"
#include "RtsVideoCapture.h"
#include "RtsSoundRestart.h"
#include "RtsArm9CpuState.h"
#include "RtsArm9RestoreState.h"
#include "RtsArm7Capture.h"
// P4.0: persistent restore experiment. Internal 3D state remains incomplete.
#define RTS_P4_MAGIC 0x30505452u
#define RTS_P4_VERSION 0x00040001u
#define RTS_P4_PAYLOAD_BYTES 0x4c9600u
#define RTS_P4_FILE_BYTES 0x4c9800u
#define RTS_P4_SOUND_OFFSET 0x4c9400u
#define RTS_P4_EXPERIMENT_FLAG 4u
#define RTS_P4_CPU_WORDS 46u
typedef struct {uint8_t code[32],build[32],session[16];} RtsP4Identity;
typedef struct {volatile uint32_t count;uint32_t data[16],padding[7];} RtsP4Queue;
typedef struct {
    volatile uint32_t error,operation,ready,release;
    uint32_t padding[4];
    RtsP4Queue to7,to9;
} RtsP4Shared;
typedef union {RtsVideoCapture video;RtsSoundShadow sound;RtsSoundRestartPlan plan;} RtsP4Scratch;
typedef struct {uint32_t aux,command0,command1,cardControl,exmem;} RtsP4CardState;
#ifdef __cplusplus
static_assert(sizeof(RtsP4Shared)==224 && sizeof(RtsP4Identity)==80);
extern "C" {
#else
_Static_assert(sizeof(RtsP4Shared)==224 && sizeof(RtsP4Identity)==80,"P4 shared ABI");
#endif
extern RtsP4Shared gRtsP4;
extern RtsP4Scratch gRtsP4Scratch;
extern RtsP4Identity gRtsP4Identity;
extern volatile uint32_t gRtsSoundBusy;
extern RtsSoundShadow gRtsSoundShadow;
extern uint32_t gRtsP4TailAddress,gRtsP4SavedSequence,gRtsP4FreshSlot;
void rtsP4Arm7Begin(uint32_t originalIpc);
void rtsP4Arm7Entry(void);
void rtsP4Arm7Loop(void);
uint32_t rtsP4Load(const RtsP4CardState*);
void rtsP4InvalidateLine(uint32_t);
uint32_t rtsP4GetControl(void);
void rtsP4Drain(void);
void rtsP4Arm9Begin(void);
uint32_t rtsP4FreezeHeader(void);
uint32_t rtsP4FreezePayload(void);
void rtsP4SealHeader(RtsM2Header*);
void rtsP4Drain9(void);
void rtsP4ReplayCurrent(void);
int rtsP4Request(uint32_t command,uint32_t block);
uint32_t RtsP4Crc(uint32_t,const uint32_t*,uint32_t);
int RtsP4ReadSector(uint32_t,uint32_t*);
void RtsP4Progress(uint32_t,uint32_t);
void RtsP4Heartbeat(uint32_t);
__attribute__((noreturn)) void RtsP4Fault(uint32_t);
#ifdef __cplusplus
}
#endif
