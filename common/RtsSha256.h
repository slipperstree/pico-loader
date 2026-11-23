#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct {uint32_t h[8];uint64_t bytes;uint32_t used;uint8_t block[64];} RtsSha256;
#ifdef __cplusplus
extern "C" {
#endif
void RtsSha256Init(RtsSha256*);
void RtsSha256Update(RtsSha256*,const void*,size_t);
void RtsSha256Finish(RtsSha256*,uint8_t out[32]);
#ifdef __cplusplus
}
#endif
