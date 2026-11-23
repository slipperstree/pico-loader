#include "RtsCheckpoint.h"
typedef uint32_t u32;typedef uint8_t u8;
static const u32 table[16]={0,0x1db71064,0x3b6e20c8,0x26d930ac,0x76dc4190,0x6b6b51f4,0x4db26158,0x5005713c,0xedb88320,0xf00f9344,0xd6d6a3e8,0xcb61b38c,0x9b64c2b0,0x86d3d2d4,0xa00ae278,0xbdbdf21c};
static u32 crc(u32 v,const u32* words,u32 n){for(u32 i=0;i<n;++i){v^=words[i];for(u32 j=0;j<8;++j)v=(v>>4)^table[v&15];}return v;}
static int equal(const u8* a,const u8* b,u32 n){u32 different=0;for(u32 i=0;i<n;++i)different|=a[i]^b[i];return !different;}
static int nonzero(const u8* a,u32 n){u32 any=0;for(u32 i=0;i<n;++i)any|=a[i];return any!=0;}
static int region(const RtsCheckpointSection* s)
{
    switch(s->kind)
    {
    case 1:return s->guestBase==0x02000000 && s->bytes==0x400000;
    case 2:return !(s->guestBase&4095) && s->guestBase>=0x02400000 && s->guestBase<=0x02ffc000 && s->bytes==0x4000;
    case 3:return s->guestBase==0x01ff8000 && s->bytes==0x8000;
    case 4:return s->guestBase==0x03800000 && s->bytes==0x10000;
    case 5:return s->guestBase==0x03000000 && s->bytes==0x8000;
    case 6:return s->guestBase==0x06800000 && s->bytes==0xa4000;
    case 7:return s->guestBase==0x05000000 && s->bytes==2048;
    case 8:return s->guestBase==0x07000000 && s->bytes==2048;
    case 9:case 10:case 11:case 12:case 13:case 14:return s->guestBase==0 && s->bytes==512;
    case 15:return s->guestBase==0 && s->bytes<=0x100000;
    default:return 0;
    }
}
int RtsInspectCheckpoint(RtsReadCheckpointSector read,void* user,u32 fileBytes,const RtsCheckpointExpected* expected,RtsCheckpointInspection* out)
{
    if(!read || !expected || !out || fileBytes<512 || (fileBytes&511) || fileBytes>0x1000000 ||
       !nonzero(expected->romSha256,32) || !nonzero(expected->buildSha256,32) || !nonzero(expected->session,16))return RTS_CK_ARGUMENT;
    RtsCheckpointHeader h;
    if(!read(user,0,&h))return RTS_CK_IO;
    if(h.magic!=RTS_CHECKPOINT_MAGIC || h.version!=RTS_CHECKPOINT_VERSION || h.headerBytes!=512 || h.fileBytes!=fileBytes ||
       h.phase!=2 || h.flags!=RTS_CHECKPOINT_DIAGNOSTIC || h.capabilities&~31u || !h.sectionCount || h.sectionCount>16)return RTS_CK_FORMAT;
    u32 headerCrc=h.headerCrc;h.headerCrc=0;
    if(~crc(~0u,(const u32*)&h,128)!=headerCrc)return RTS_CK_HEADER_CRC;
    h.headerCrc=headerCrc;
    if(h.gameCode!=expected->gameCode || h.sdkVersion!=expected->sdkVersion ||
       !equal(h.romSha256,expected->romSha256,32) || !equal(h.buildSha256,expected->buildSha256,32) ||
       !equal(h.session,expected->session,16))return RTS_CK_IDENTITY;
    u32 cursor=512,mask=0;
    for(u32 i=0;i<16;++i)
    {
        const RtsCheckpointSection* s=&h.sections[i];
        if(i>=h.sectionCount){if(s->kind || s->offset || s->bytes || s->crc || s->guestBase || s->flags)return RTS_CK_LAYOUT;continue;}
        if(!s->kind || s->kind>15 || !s->bytes || s->bytes&511 || s->offset!=cursor || cursor>fileBytes ||
           s->bytes>fileBytes-cursor || s->flags || mask&(1u<<s->kind) || !region(s))return RTS_CK_LAYOUT;
        mask|=1u<<s->kind;cursor+=s->bytes;
    }
    if(cursor!=fileBytes)return RTS_CK_LAYOUT;
    u32 buffer[128],payload=~0u;
    for(u32 i=0;i<h.sectionCount;++i)
    {
        const RtsCheckpointSection* s=&h.sections[i];u32 section=~0u;
        for(u32 offset=0;offset<s->bytes;offset+=512)
        {
            if(!read(user,(s->offset+offset)/512,buffer))return RTS_CK_IO;
            section=crc(section,buffer,128);payload=crc(payload,buffer,128);
        }
        if(~section!=s->crc)return RTS_CK_SECTION_CRC;
    }
    if(~payload!=h.payloadCrc)return RTS_CK_PAYLOAD_CRC;
    // Atomic publication only after full read. Never imply complete device/CPU
    // semantics or authorize memory writes merely from section flags/CRC.
    out->integrityVerified=1;out->identityMatched=1;out->allowRestore=0;out->sectionMask=mask;
    u32* target=(u32*)&out->header;const u32* source=(const u32*)&h;
    for(u32 i=0;i<128;++i)target[i]=source[i];
    return RTS_CK_OK;
}
