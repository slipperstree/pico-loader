#pragma once
#include <stdint.h>
#define RTS_SOUND_SHADOW_MAGIC 0x31485341u
#define RTS_SOUND_PLAN_MAGIC 0x31525341u
typedef struct {uint32_t control,source,timer,loop,length;} RtsSoundChannel;
typedef struct {
    uint32_t magic,version,sequence,unsupported;
    RtsSoundChannel channels[16];
    uint32_t coverage[16],reserved[28];
} RtsSoundShadow;
typedef struct {
    uint32_t magic,version,master,bias,activeMask,sequence;
    RtsSoundChannel channels[16];
    uint32_t reserved[42];
} RtsSoundRestartPlan;
typedef void (*RtsSoundWrite)(void*,uint32_t address,uint32_t bytes,uint32_t value);
#ifdef __cplusplus
static_assert(sizeof(RtsSoundShadow)==512 && sizeof(RtsSoundRestartPlan)==512);
extern "C" {
#else
_Static_assert(sizeof(RtsSoundShadow)==512 && sizeof(RtsSoundRestartPlan)==512,"sound ABI");
#endif
#ifdef _WIN32
#define RTS_SOUND_API __declspec(dllexport)
#else
#define RTS_SOUND_API
#endif
RTS_SOUND_API void RtsInitSoundShadow(RtsSoundShadow*);
RTS_SOUND_API int RtsObserveSoundWrite(RtsSoundShadow*,uint32_t address,uint32_t bytes,uint32_t value);
RTS_SOUND_API int RtsBuildSoundRestart(const RtsSoundShadow*,const uint32_t liveControl[16],uint32_t master,uint32_t bias,uint32_t captureControl,RtsSoundRestartPlan*);
// Unlinked research. Caller validates whole checkpoint and restores sample RAM
// before Prepare. Release only after both CPUs and device state are coherent.
// Intentionally restarts samples; does not recover their internal play position.
RTS_SOUND_API void RtsPrepareSoundRestart(const RtsSoundRestartPlan*,RtsSoundWrite,void*);
RTS_SOUND_API void RtsReleaseSoundRestart(const RtsSoundRestartPlan*,RtsSoundWrite,void*);
#ifdef __cplusplus
}
#endif
