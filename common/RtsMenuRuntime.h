#pragma once
#include "RtsMenu.h"
#include "RtsSnapshotInfo.h"
#define RTS_MENU_BOOT_MAGIC 0x36554d52u
#define RTS_MENU_META_MAGIC 0x31544d52u
#define RTS_MENU_C_SECTOR 0u
#define RTS_MENU_D_SECTOR 256u
#define RTS_MENU_CAPTURE_SECTOR 512u
#define RTS_MENU_SLOT_META_SECTOR 532u
#define RTS_MENU_THUMB_SECTORS 20u
#define RTS_MENU_AUX_HEADER_SECTOR 616u
#define RTS_MENU_MAP_SECTOR 617u
#define RTS_MENU_H_SECTOR 620u
#define RTS_MENU_IMAGE_SECTOR 684u
#define RTS_MENU_RELOC_SECTOR 748u
#define RTS_MENU_AUX_SECTORS 756u
typedef struct {uint32_t magic,debug;RtsSnapshotInfo aux;uint32_t oldBankH;} RtsMenuCoreBoot;
typedef struct {
 uint32_t magic,debug;
 RtsSnapshotInfo slots[4],aux;
} RtsMenuBoot;
typedef struct {
 uint32_t magic,version,gameCode,sequence;
 RtsMenuTime time;
 uint32_t hasThumbnail,reserved[121];
} RtsMenuMetadata;
#ifdef __cplusplus
static_assert(sizeof(RtsMenuMetadata)==512);
extern "C" {
#else
_Static_assert(sizeof(RtsMenuMetadata)==512,"menu metadata sector");
#endif
extern RtsMenuBoot gRtsMenuBoot;
extern RtsMenuCoreBoot gRtsMenuCoreBoot;
extern uint32_t gRtsMenuLoaded;
void RtsMenuLoadOverlay(void);
void RtsMenuUnloadOverlay(void);
int RtsMenuRuntimeOpen(void);
void RtsMenuRuntimeClose(void);
void RtsMenuRuntimeProgress(uint32_t,uint32_t);
void RtsMenuRuntimeSaved(uint32_t);
int RtsMenuRuntimeReadVideo(uint32_t,uint16_t*);
int RtsMenuRuntimeWriteVideo(uint32_t,const uint16_t*);
void RtsMenuRuntimeFinishLoad(void);
int RtsMenuRawRead(const RtsSnapshotInfo*,uint32_t,uint32_t*);
int RtsMenuRawWrite(const RtsSnapshotInfo*,uint32_t,const uint32_t*);
void RtsMenuReadClock7(void*);
#ifdef __cplusplus
}
#endif
