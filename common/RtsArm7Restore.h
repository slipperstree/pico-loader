#pragma once
#include "RtsArm7Capture.h"
typedef int (*RtsReadArm7Bytes)(void*,uint32_t,void*,uint32_t);
enum RtsArm7RestoreResult {RTS_A7_OK,RTS_A7_UNVERIFIED,RTS_A7_CONTEXT,RTS_A7_MODE,RTS_A7_RANGE,RTS_A7_FRAME,RTS_A7_READ};
#ifdef __cplusplus
extern "C" {
#endif
#ifdef _WIN32
__declspec(dllexport)
#endif
int RtsValidateArm7Continuation(const RtsArm7Context*,uint32_t workspace,uint32_t bytes,int payloadVerified,RtsReadArm7Bytes,void*);
// Research primitives only. NOT linked into any live loader. Caller must
// validate full state/identity and coordinate both CPUs before using these.
// Writer requires masked IRQ/FIQ, IME=0, and main-RAM source and return code.
int rtsArm7RestoreSector(uint32_t block,const uint32_t data[128]);
void rtsEnterArm7Continuation(const RtsArm7Context*);
#ifdef __cplusplus
}
#endif
