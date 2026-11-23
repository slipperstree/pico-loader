#pragma once
#include <stdint.h>
#define RTS_CHECKPOINT_MAGIC 0x34435452u
#define RTS_CHECKPOINT_VERSION 0x00040001u
#define RTS_CHECKPOINT_DIAGNOSTIC 1u
#define RTS_CHECKPOINT_MAX_SECTIONS 16u
typedef struct {uint32_t kind,offset,bytes,crc,guestBase,flags;} RtsCheckpointSection;
typedef struct {
    uint32_t magic,version,headerBytes,fileBytes,gameCode,sdkVersion,capabilities,phase;
    uint8_t romSha256[32],buildSha256[32],session[16];
    uint32_t sectionCount,headerCrc,payloadCrc,flags;
    RtsCheckpointSection sections[16];
} RtsCheckpointHeader;
typedef struct {
    uint32_t gameCode,sdkVersion;
    uint8_t romSha256[32],buildSha256[32],session[16];
} RtsCheckpointExpected;
typedef struct {
    uint32_t integrityVerified,identityMatched,allowRestore,sectionMask;
    RtsCheckpointHeader header;
} RtsCheckpointInspection;
typedef int (*RtsReadCheckpointSector)(void*,uint32_t,void*);
enum RtsCheckpointResult {RTS_CK_OK,RTS_CK_ARGUMENT,RTS_CK_IO,RTS_CK_FORMAT,RTS_CK_HEADER_CRC,RTS_CK_IDENTITY,RTS_CK_LAYOUT,RTS_CK_SECTION_CRC,RTS_CK_PAYLOAD_CRC};
#ifdef __cplusplus
static_assert(sizeof(RtsCheckpointHeader)==512);
extern "C" {
#else
_Static_assert(sizeof(RtsCheckpointHeader)==512,"checkpoint manifest ABI");
#endif
#ifdef _WIN32
__declspec(dllexport)
#endif
int RtsInspectCheckpoint(RtsReadCheckpointSector,void*,uint32_t actualFileBytes,const RtsCheckpointExpected*,RtsCheckpointInspection*);
// Read-only integrity/identity stage, NOT a restore authorizer. No write callback
// exists. Output is published only after all file sectors pass. Current version
// accepts diagnostic manifests only and always returns allowRestore=0.
#ifdef __cplusplus
}
#endif
