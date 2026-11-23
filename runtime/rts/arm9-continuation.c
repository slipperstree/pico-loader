#include "RtsArm9Continuation.h"
typedef uint32_t u32;
static int within(u32 address,u32 bytes,u32 base,u32 size)
{
    return address>=base && bytes<=size && address-base<=size-bytes;
}
static int capturedStack(const RtsM2Header* h,u32 address,u32 bytes)
{
    if(within(address,bytes,0x02000000,0x400000))
        return address+bytes<=h->workspaceBase || address>=h->workspaceBase+h->workspaceBytes;
    return within(address,bytes,h->dtcmBase,0x4000);
}
static int knownLayout(const RtsM2Header* h)
{
    return (h->magic==0x30505452 && h->version==0x40001 && h->fileBytes==0x4c9800 && h->payloadBytes==0x4c9600) ||
           (h->magic==0x324d5452 && h->version==0x20001 && h->fileBytes==0x40c200 && h->payloadBytes==0x40c000) ||
           (h->magic==0x31435452 && h->version==0x30001 && h->fileBytes==0x424400 && h->payloadBytes==0x424200) ||
           (h->magic==0x32565452 && h->version==0x30002 && h->fileBytes==0x4c9600 && h->payloadBytes==0x4c9400);
}
static int secure(u32 address,u32 bytes){return within(address,bytes,0x02000000,0x800);}
int RtsBuildArm9Continuation(const RtsM2Header* h,int payloadVerified,
    RtsReadCapturedBytes read,void* user,RtsArm9Continuation* out)
{
    if(!payloadVerified)return RTS_CONTINUATION_UNVERIFIED;
    if(!h || !read || !out || !knownLayout(h) ||
       h->gameCode!=RTS_M2_GAME || h->phase!=2 || h->error || ((h->magic==0x30505452) ? (h->flags!=4 && h->flags!=6) : (h->flags!=1 && h->flags!=3)) ||
       h->dtcmBytes!=0x4000 || h->itcmBase!=0x01ff8000 || h->itcmBytes!=0x8000 ||
       h->dtcmBase<0x02400000 || h->dtcmBase>0x02ffc000 || (h->dtcmBase&0xfff) ||
       !h->workspaceBytes || (h->workspaceBase&511) || (h->workspaceBytes&511) ||
       h->workspaceBase<0x02300000 || h->workspaceBase>=0x023ff000 ||
       h->workspaceBytes>0x023ff000-h->workspaceBase)return RTS_CONTINUATION_HEADER;
    if((h->gateCpsr&0x010000bf)!=0x1f)return RTS_CONTINUATION_MODE;
    u32 sp=h->regs[13],lr=h->regs[14],pc=lr&~1u;
    if((h->frameAddress&3) || h->frameAddress<56 || h->frameAddress>UINT32_MAX-48 ||
       sp!=h->frameAddress+48 || !capturedStack(h,h->frameAddress-56,104) ||
       !capturedStack(h,sp,(lr&1) ? 20 : 24))return RTS_CONTINUATION_RANGE;
    u32 frame[12],entry[14];
    if(!read(user,h->frameAddress,frame,sizeof(frame)) ||
       !read(user,h->frameAddress-56,entry,sizeof(entry)))return RTS_CONTINUATION_READ;
    if(frame[4]!=h->gateCpsr || frame[10]!=h->regs[12] || frame[11]!=lr ||
       entry[12]!=h->reserved[0] || entry[13]!=h->regs[15])return RTS_CONTINUATION_FRAME;
    for(u32 i=0;i<4;++i)if(frame[6+i]!=h->regs[i])return RTS_CONTINUATION_FRAME;
    for(u32 i=4;i<12;++i)if(entry[i]!=h->regs[i])return RTS_CONTINUATION_FRAME;
    u32 gate;
    if(lr&1)
    {
        if(pc<6 || !secure(pc-6,16))return RTS_CONTINUATION_STUB;
        uint16_t stub[8];
        if(!read(user,pc-6,stub,sizeof(stub)))return RTS_CONTINUATION_READ;
        if(stub[0]!=0xb50f || stub[1]!=0x4b02 || stub[2]!=0x4798 || stub[3]!=0xbc0f ||
           stub[4]<0xdf03 || stub[4]>0xdf06 || stub[5]!=0xbd00)return RTS_CONTINUATION_STUB;
        gate=(u32)stub[6]|((u32)stub[7]<<16);
        if(h->regs[3]!=gate)return RTS_CONTINUATION_FRAME;
    }
    else
    {
        if((pc&3) || pc<12 || !secure(pc-12,32))return RTS_CONTINUATION_STUB;
        u32 stub[8];
        if(!read(user,pc-12,stub,sizeof(stub)))return RTS_CONTINUATION_READ;
        if(stub[0]!=0xe92d500f || stub[1]!=0xe59fc00c || stub[2]!=0xe12fff3c ||
           stub[3]!=0xe8bd500f || (stub[4]&0xffff0fff)!=0xee070f90 ||
           (stub[4]&0xf000)==0xf000 || stub[5]!=0xe59ff000 ||
           !(within(stub[7],4,0x02000804,0x3ff7fc) || within(stub[7],4,0x01ff8004,0x7ffc)))
            return RTS_CONTINUATION_STUB;
        u32 branch;
        if(!read(user,stub[7]-4,&branch,4))return RTS_CONTINUATION_READ;
        u32 delta=(branch&0xffffff)<<2;
        if(delta&0x02000000)delta|=0xfc000000;
        if((branch>>24)!=0xea || stub[7]+4+delta!=pc-12)return RTS_CONTINUATION_STUB;
        gate=stub[6];
        if(h->regs[12]!=gate)return RTS_CONTINUATION_FRAME;
    }
    u32 gateStart;
    if((gate&3) || !secure(gate,4))return RTS_CONTINUATION_STUB;
    if(!read(user,gate,&gateStart,4))return RTS_CONTINUATION_READ;
    if(gateStart!=0xe92d500f)return RTS_CONTINUATION_STUB;
    RtsArm9Continuation result;
    result.cpsr=h->gateCpsr|((lr&1) ? 0x20u : 0);
    result.systemSp=sp;result.systemLr=lr;
    for(u32 i=0;i<13;++i)result.frame[i]=h->regs[i];
    result.frame[13]=pc;
    *out=result;
    return RTS_CONTINUATION_OK;
}
